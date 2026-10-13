#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hito 08 (EXPERIMENTAL): poblacion mixta SUMO + Vine con penetracion reproducible.

Se instala JUNTO a los scripts H03/H04/H06 y REUTILIZA sus funciones congeladas.
No procesa POLIDriving original ni vuelve a calcular transiciones temporales.
No cambia rutas, semaforos, tipo de vehiculo ni speedMode; la unica accion
vehicular autorizada es setAcceleration, durante un paso SUMO, tras el filtro H06.

IMPORTANTE: la seleccion porcentual es por hash determinista del ID y refleja
una probabilidad de pertenencia a la cohorte; la proporcion observada puede
diferir del porcentaje nominal.  NO demuestra fidelidad naturalista, equidad,
seguridad real ni robustez RL.  La escala temporal requiere calibracion externa.

Integracion con RL: crear StressInjector(...) con los artefactos disponibles;
llamar injector.on_step(traci, step) DESPUES de la unica simulationStep que
hace el bucle principal RL. Nunca se abre una segunda conexion TraCI.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

import ntvc_vine_r_06_piloto_integracion_protegida as h06

VERSION = 'NTVC-Vine-R H08 Estres Porcentual EXPERIMENTAL v1'


def hash_score(seed: int, vehicle_id: str) -> float:
    """U(0,1) estable por ID+semilla; anidado al variar la penetracion."""
    value = hashlib.sha256(f'{int(seed)}|{vehicle_id}'.encode('utf-8')).digest()
    return int.from_bytes(value[:8], 'big') / 2**64


def order_score(seed: int, step: int, vehicle_id: str) -> int:
    """Desempate determinista distinto por paso para evitar sesgo del ID bajo."""
    return int.from_bytes(hashlib.sha256(
        f'{int(seed)}|{int(step)}|{vehicle_id}|orden'.encode('utf-8')).digest()[:8], 'big')


@dataclass(frozen=True)
class StressConfig:
    mode: str = 'probe'
    variant: str | None = 'vine_student'
    seed: int = 101
    penetration: float = 0.15
    step_length: float = 0.5
    max_commands: int = 500
    max_commands_per_step: int = 2
    max_commands_per_window: int = 20
    window_seconds: float = 60.0
    max_commands_per_vehicle: int = 12
    cooldown_steps: int = 8
    start_time: float = 0.0
    end_time: float = math.inf
    moving_min_kmh: float = 5.0
    max_speed_kmh: float = 50.0
    amin: float = -4.0
    amax: float = 2.5
    jmax: float = 5.0
    free_gap_m: float = 60.0
    follower_gap_m: float = 60.0
    distance_to_lane_end_m: float = 60.0
    tls_distance_m: float = 80.0
    max_command_delta_a: float = 0.8

    def validate(self):
        if self.mode not in ('baseline', 'probe', 'active'):
            raise ValueError('mode debe ser baseline, probe o active.')
        if self.mode != 'baseline' and self.variant not in h06.VARIANTS:
            raise ValueError('Variante no reconocida por el nucleo H06.')
        if self.mode == 'baseline' and self.variant is not None:
            raise ValueError('Baseline no puede tener variante Vine.')
        if not math.isfinite(self.penetration) or not 0 <= self.penetration <= 1:
            raise ValueError('penetration debe estar entre 0 y 1.')
        if not 0.1 <= self.step_length <= 0.6:
            raise ValueError('dt debe ser 0.1..0.6 s en esta integracion experimental.')
        for name in ('max_commands', 'max_commands_per_step', 'max_commands_per_window',
                     'max_commands_per_vehicle'):
            if getattr(self, name) < 1:
                raise ValueError(f'{name} debe ser >= 1.')
        if self.cooldown_steps < 0:
            raise ValueError('cooldown_steps no puede ser negativo.')
        if self.window_seconds <= 0 or not math.isfinite(self.window_seconds):
            raise ValueError('window_seconds debe ser positivo y finito.')
        if (not math.isfinite(self.start_time) or self.start_time < 0 or
            self.end_time <= self.start_time):
            raise ValueError('Intervalo temporal incorrecto.')
        if self.amin >= self.amax or self.jmax <= 0 or self.max_command_delta_a < 0:
            raise ValueError('Limites cinematicos invalidos.')
        for name in ('moving_min_kmh', 'max_speed_kmh', 'free_gap_m', 'follower_gap_m',
                     'distance_to_lane_end_m', 'tls_distance_m'):
            if getattr(self, name) < 0:
                raise ValueError(f'{name} no puede ser negativo.')


class StressInjector:
    """Inyector acoplable al MISMO TraCI del controlador de semaforos.

    on_step() no llama simulationStep(); el controlador de RL decide el orden
    de actuacion y lo documenta. Se conserva una historia por vehiculo admitido.
    """

    def __init__(self, config: StressConfig, kernel=None, groups=None):
        config.validate()
        if config.mode in ('probe', 'active') and config.penetration > 0 and kernel is None:
            raise ValueError('Falta nucleo Vine precargado; use load_frozen_cohorts().')
        self.cfg = config
        self.kernel = kernel
        self.groups = groups
        self.history = {}
        self.pending = {}
        self.seen = {}  # id -> primer tiempo, seleccion, hash; se fija al primer avistamiento
        self.commanded_ids = set()
        self.counts = Counter()
        self.commands_per_vehicle = Counter()
        self.commands_per_window = Counter()
        self.last_command_step = {}
        self.command_count = 0
        self.safety_halt = False
        self.rows = []
        self.fleet = []
        self._last_time = -math.inf
        self._last_step = -1

    def _membership(self, vid):
        score = hash_score(self.cfg.seed, vid)
        return (score < self.cfg.penetration), score

    def on_step(self, traci, step: int):
        """Llamar una vez por paso, DESPUES de simulationStep() del bucle SUMO/RL."""
        if step <= self._last_step:
            raise RuntimeError('on_step duplicado o fuera de orden.')
        cfg = self.cfg
        sim = traci.simulation
        t = float(sim.getTime())
        dt = float(sim.getDeltaT())
        if t <= self._last_time or not math.isfinite(t):
            raise RuntimeError('Tiempo SUMO no creciente o no finito.')
        if not math.isfinite(dt) or dt <= 0:
            raise RuntimeError('DeltaT SUMO invalido.')
        if cfg.mode == 'active' and (not 0.1 <= dt <= 0.6 or
                                     abs(dt-cfg.step_length) > 1e-6):
            raise RuntimeError('DeltaT distinto del autorizado. NO se aplica control.')
        self._last_step = step
        self._last_time = t

        ids = sorted(set(map(str, traci.vehicle.getIDList())))
        for vid in ids:
            if vid not in self.seen:
                selected, score = self._membership(vid)
                self.seen[vid] = dict(vehicle_id=vid, first_seen_time_s=t,
                                      hash_score=score, selected=selected)
        present = set(ids)
        selected_now = {v for v in ids if self.seen[v]['selected']}
        for vid in list(self.history):
            if vid not in selected_now:
                self.history.pop(vid, None)
        for vid, rec in list(self.pending.items()):
            if vid in present:
                rec['observed_a_next'] = float(traci.vehicle.getAcceleration(vid))
                rec['observed_speed_next_kmh'] = 3.6 * float(traci.vehicle.getSpeed(vid))
                rec['matched_t_plus_dt'] = abs(float(rec['target_time_s'])-t) < 1e-5
            self.pending.pop(vid, None)

        speeds = np.array([float(traci.vehicle.getSpeed(vid)) for vid in ids], dtype=float)
        if not np.isfinite(speeds).all():
            raise RuntimeError('SUMO reporta velocidades no finitas.')
        metrics = h06.sim_counts(sim, need_safety=(cfg.mode == 'active'))
        if cfg.mode == 'active' and (int(metrics.get('collisions') or 0) > 0 or
                                     int(metrics.get('teleport_start') or 0) > 0):
            self.safety_halt = True  # permanente por episodio; fail closed
        self.fleet.append(dict(step=step, time_s=t, dt_s=dt,
            n_active_vehicles=len(ids),
            n_selected_active_vehicles=len(selected_now),
            n_halted_vehicles=int(np.sum(speeds < 0.1)),
            mean_speed_kmh=float(np.mean(speeds)*3.6) if len(ids) else math.nan,
            **metrics))

        if cfg.mode == 'baseline' or not (cfg.start_time <= t < cfg.end_time):
            return
        # Distribuimos el presupuesto entre ventanas temporales, no agotarlo en t<10 s.
        window = int(max(0, t-cfg.start_time) // cfg.window_seconds)
        commands_this_step = 0
        ordered = sorted(selected_now, key=lambda v: (order_score(cfg.seed, step, v), v))
        for vid in ordered:
            v = float(traci.vehicle.getSpeed(vid))
            a = float(traci.vehicle.getAcceleration(vid))
            if not math.isfinite(v) or not math.isfinite(a) or v <= cfg.moving_min_kmh/3.6:
                self.history.pop(vid, None)
                self.counts['not_moving'] += 1
                continue
            hist = self.history.setdefault(vid, h06.ShadowHistory())
            hist.push(a)
            if not hist.ready:
                self.counts['history_insufficient'] += 1
                continue
            reason, context = h06.strictly_safe_context(traci, vid, cfg)
            self.counts[reason] += 1
            if reason != 'eligible':
                continue
            seed = h06.deterministic_seed(cfg.seed, vid, step)
            proposer = h06.CausalVineProposer(
                self.kernel, self.groups, cfg.variant,
                hist.values[-2], hist.values[-1], seed)
            proposed = float(proposer.propose())
            if not math.isfinite(proposed):
                self.counts['nonfinite_proposal'] += 1
                continue
            guard = h06.guard_step(context['speed'], hist.values[-1], proposed, dt,
                amin=cfg.amin, amax=cfg.amax, jmax=cfg.jmax,
                vmax=context['speed_limit'])
            breakdown = h06.classify_constraints(
                context['speed'], hist.values[-1], proposed, dt,
                context['speed_limit'], guard, amin=cfg.amin,
                amax=cfg.amax, jmax=cfg.jmax)
            target = float(guard['applied_a'])
            rec = dict(mode=cfg.mode, variant=cfg.variant, seed=cfg.seed,
                penetration_requested=cfg.penetration, step=step, time_s=t,
                target_time_s=t+dt, vehicle_id=vid,
                observed_a=a, speed_kmh=3.6*v, proposed_a=proposed,
                guarded_a=target, guard_reason=guard['feasibility'],
                guard_intervened=bool(guard['intervened']),
                delta_from_current_a=target-a,
                observed_a_next=math.nan, observed_speed_next_kmh=math.nan,
                matched_t_plus_dt=False, command_issued=False,
                action_decision='', **breakdown)
            if guard['feasibility'] != 'feasible' or guard['jerk_limit_breached']:
                rec['action_decision'] = 'guard_infeasible'
            elif abs(target-a) > cfg.max_command_delta_a:
                rec['action_decision'] = 'proposal_too_far_from_nominal'
            elif cfg.mode == 'probe':
                self.counts['action_viable'] += 1
                rec['action_decision'] = 'probe_only'
                self.pending[vid] = rec
            elif self.safety_halt:
                rec['action_decision'] = 'safety_halt_collision_or_teleport'
            elif self.command_count >= cfg.max_commands:
                rec['action_decision'] = 'total_command_quota'
            elif commands_this_step >= cfg.max_commands_per_step:
                rec['action_decision'] = 'step_command_quota'
            elif self.commands_per_window[window] >= cfg.max_commands_per_window:
                rec['action_decision'] = 'window_command_quota'
            elif self.commands_per_vehicle[vid] >= cfg.max_commands_per_vehicle:
                rec['action_decision'] = 'vehicle_command_quota'
            elif (vid in self.last_command_step and
                  step - self.last_command_step[vid] <= cfg.cooldown_steps):
                rec['action_decision'] = 'cooldown'
            else:
                # UNICA instruccion que interviene dinamicamente en la simulacion.
                # strictly_safe_context() ha comprobado speedMode=31.
                traci.vehicle.setAcceleration(vid, target, dt)
                self.command_count += 1
                commands_this_step += 1
                self.commands_per_window[window] += 1
                self.commands_per_vehicle[vid] += 1
                self.commanded_ids.add(vid)
                self.last_command_step[vid] = step
                self.counts['action_viable'] += 1
                rec['command_issued'] = True
                rec['action_decision'] = 'command_issued'
                self.pending[vid] = rec
            self.rows.append(rec)

    def results(self):
        total_seen = len(self.seen)
        selected_count = sum(bool(v['selected']) for v in self.seen.values())
        meta = dict(mode=self.cfg.mode, variant=self.cfg.variant, seed=self.cfg.seed,
            penetration_requested=self.cfg.penetration,
            penetration_seen=(selected_count/total_seen if total_seen else None),
            penetration_actuated=(len(self.commanded_ids)/total_seen if total_seen else None),
            n_seen_vehicles=total_seen, n_selected_vehicles=selected_count,
            n_vehicles_commanded=len(self.commanded_ids),
            n_steps=len(self.fleet), n_safety_eligible=int(self.counts['eligible']),
            n_action_viable=int(self.counts['action_viable']),
            n_commands=self.command_count, safety_halt=self.safety_halt,
            commands_by_window=dict(sorted(self.commands_per_window.items())),
            reasons=dict(self.counts), remaining_pending=len(self.pending))
        return (pd.DataFrame(self.rows), pd.DataFrame(self.fleet),
                pd.DataFrame(sorted(self.seen.values(), key=lambda r: r['vehicle_id'])), meta)


def load_frozen_cohorts(data_dir: Path, config: StressConfig):
    """Reusa read_artifacts + fit_fold del H06, misma semilla y parametros estadisticos.

    NOTA: fit_fold reestima deterministamente desde las cohortes H01 congeladas,
    igual que H06; no entrena nuevamente desde los CSV originales PoliDriving.
    """
    if config.mode == 'baseline' or config.penetration == 0:
        return None, None, None, None, None
    samples, input_manifest = h06.read_artifacts(data_dir)
    # H06 usa FIT_SEED+100 y FIT_SEED+100*71; conservar EXACTAMENTE las semillas.
    fit_args = argparse.Namespace(bins_per_sign=8, max_fit=2000,
                                  moving_min_kmh=5.0)
    kernel, groups, tables, n_pairs = h06.fit_fold(samples, h06.FIT_SEED+100,
        fit_args, copula_seed=h06.FIT_SEED+100*71)
    return kernel, groups, tables, n_pairs, input_manifest


def self_test():
    # Pruebas puras sin SUMO ni datos reales: anidamiento, independencia de orden,
    # validaciones y ausencia de actuacion en penetracion 0.
    ids = [f'veh_{i}' for i in range(1000)]
    a = {v for v in ids if hash_score(101, v) < .15}
    b = {v for v in ids if hash_score(101, v) < .30}
    c = {v for v in ids if hash_score(101, v) < .50}
    assert a <= b <= c
    assert [v for v in ids if hash_score(101,v)<.30] == [v for v in reversed(ids)
             if hash_score(101,v)<.30][::-1]
    assert not {v for v in ids if hash_score(101,v)<0}
    try:
        StressConfig(mode='active', penetration=1.1).validate()
    except ValueError: pass
    else: raise AssertionError('Penetracion 1.1 no fue rechazada.')
    try:
        StressConfig(mode='active', step_length=1.0).validate()
    except ValueError: pass
    else: raise AssertionError('dt=1 no fue rechazado.')
    assert StressConfig(mode='baseline', variant=None, penetration=0).validate() is None
    print('SELF-TEST H08 OK: seleccion anidada, determinismo, dt y limites.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--mode', choices=('baseline','probe','active'), default='probe')
    parser.add_argument('--variant', choices=h06.VARIANTS, default=None)
    parser.add_argument('--penetration', type=float, default=.15,
                        help='Fraccion probabilistica de IDs (0 a 1), NO cuota exacta.')
    parser.add_argument('--ack-active', default='')
    parser.add_argument('--ack-time-scale', default='')
    parser.add_argument('--sumo-config', type=Path)
    parser.add_argument('--sumo-binary')
    parser.add_argument('--data-dir', type=Path, default=h06.DEFAULT_DATA)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--sumo-steps', type=int, default=600)
    parser.add_argument('--step-length', type=float, default=.5)
    parser.add_argument('--seed', type=int, default=101)
    parser.add_argument('--max-commands', type=int, default=500)
    parser.add_argument('--max-commands-per-step', type=int, default=2)
    parser.add_argument('--max-commands-per-window', type=int, default=20)
    parser.add_argument('--window-seconds', type=float, default=60.)
    parser.add_argument('--max-commands-per-vehicle', type=int, default=12)
    parser.add_argument('--cooldown-steps', type=int, default=8)
    parser.add_argument('--start-time', type=float, default=0.)
    parser.add_argument('--end-time', type=float, default=math.inf)
    # Valores identicos a H06; se exponen para auditoria sin modificar H03/H04.
    parser.add_argument('--moving-min-kmh', type=float, default=5.0)
    parser.add_argument('--max-speed-kmh', type=float, default=50.0)
    parser.add_argument('--amin', type=float, default=-4.0)
    parser.add_argument('--amax', type=float, default=2.5)
    parser.add_argument('--jmax', type=float, default=5.0)
    parser.add_argument('--free-gap-m', type=float, default=60.0)
    parser.add_argument('--follower-gap-m', type=float, default=60.0)
    parser.add_argument('--distance-to-lane-end-m', type=float, default=60.0)
    parser.add_argument('--tls-distance-m', type=float, default=80.0)
    parser.add_argument('--max-command-delta-a', type=float, default=0.8)
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.mode == 'baseline':
        if args.variant is not None:
            parser.error('Baseline no acepta --variant.')
    elif args.variant is None:
        args.variant='vine_student'
    if args.mode == 'active' and (args.ack_active != h06.ACTIVE_ACK or
                                  args.ack_time_scale != h06.TIME_ACK):
        parser.error('Active requiere --ack-active EXPERIMENTAL_ONLY '
                     '--ack-time-scale NOT_CALIBRATED.')
    if args.sumo_config is None or args.output is None:
        parser.error('Se requieren --sumo-config y --output.')
    if args.sumo_steps < 5:
        parser.error('--sumo-steps debe ser >=5.')
    cfg = StressConfig(**{k:getattr(args,k) for k in StressConfig.__dataclass_fields__})
    cfg.validate()
    config_file = args.sumo_config.resolve()
    if not config_file.is_file():
        raise FileNotFoundError(config_file)
    out = args.output.resolve()
    approved_root = (h06.ROOT/'resultados').resolve()
    if approved_root not in out.parents or out.exists():
        raise ValueError('--output debe ser carpeta NUEVA dentro de revision_naturalista/resultados.')
    inp_hashes = h06.sumo_input_hashes(config_file)
    if any(v == 'UNRESOLVED' for v in inp_hashes.values()):
        raise RuntimeError('Inputs no resueltos. NO iniciar experimentos.')
    kernel, groups, tables, n_pairs, dataset_manifest = load_frozen_cohorts(
        args.data_dir, cfg)
    try:
        import traci
    except ImportError:
        import os
        home = os.environ.get('SUMO_HOME')
        if home:
            sys.path.insert(0, str(Path(home)/'tools'))
        import traci
    binary = args.sumo_binary or shutil.which('sumo')
    if not binary:
        raise RuntimeError('SUMO no esta disponible en PATH; use --sumo-binary.')
    injector = StressInjector(cfg, kernel, groups)
    out.mkdir(parents=True, exist_ok=False)
    command = [str(binary), '-c', str(config_file), '--seed', str(args.seed),
               '--output-prefix', str(out/'sumo_'), '--step-length', str(cfg.step_length)]
    print('COMANDO SUMO:', ' '.join(command), flush=True)
    print('H08 MODO:', cfg.mode, 'VINE:', cfg.variant,
          'PENETRACION:', cfg.penetration, flush=True)
    if cfg.mode == 'active':
        print('AVISO: piloto EXPERIMENTAL; escala temporal NO calibrada.', flush=True)
    try:
        traci.start(command)
        try:
            for step in range(args.sumo_steps):
                traci.simulationStep()
                injector.on_step(traci, step)
                if traci.simulation.getMinExpectedNumber() == 0:
                    break
        finally:
            traci.close()
    except Exception:
        # Dejar outputs/logs parciales en su carpeta, no declarar exito.
        raise
    actions, fleet, assignment, meta = injector.results()
    files = {'acciones_hito08.csv':actions, 'trafico_hito08.csv':fleet,
             'asignacion_hito08.csv':assignment}
    if tables is not None:
        files['familias_hito08_train.csv'] = tables
    for name, table in files.items():
        table.to_csv(out/name, index=False, float_format='%.12g')
    manifest = dict(version=VERSION, source_sumo_config=str(config_file),
        sumo_command=command, sumo_scenario_input_sha256=inp_hashes,
        source_h06_sha256=h06.sha256(Path(h06.__file__).resolve()),
        source_h03_sha256=h06.sha256(Path(h06.__file__).resolve().parent/
            'ntvc_vine_r_03_integracion_cinematica_sumo.py'),
        source_h04_sha256=h06.sha256(Path(h06.__file__).resolve().parent/
            'ntvc_vine_r_04_shadow_multivehiculo_rutas_corregidas.py'),
        frozen_hito01_manifest_sha256=(h06.sha256(args.data_dir/'manifest.json')
             if dataset_manifest is not None else None),
        n_training_pairs=n_pairs, metadata=meta,
        params={k:('unbounded' if isinstance(v,float) and math.isinf(v) else v)
                for k,v in vars(args).items()
                if k not in ('ack_active','ack_time_scale') and not isinstance(v,Path)},
        output_sha256={name:h06.sha256(out/name) for name in files},
        caveats=[
          'Penetracion por hash de IDs: porcentaje observado NO exactamente nominal.',
          'No se validan naturalismo ni seguridad real.',
          'Paso temporal POLIDriving-SUMO NO calibrado.',
          'Filtro de via libre H06 puede reducir drasticamente penetracion efectiva.',
          'Integracion RL requiere MISMA conexion TraCI y control compartido por paso.',
          'La equidad requiere metricas por vehiculo/ruta; no se garantiza por este inyector.'])
    (out/'manifest_hito08.json').write_text(json.dumps(manifest, indent=2,
        ensure_ascii=False, allow_nan=False), encoding='utf-8')
    print('RESUMEN HITO08:', json.dumps(meta, ensure_ascii=False), flush=True)
    print('SALIDA:', out, flush=True)


if __name__ == '__main__':
    main()
