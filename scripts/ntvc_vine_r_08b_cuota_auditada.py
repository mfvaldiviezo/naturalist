#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H08b: piloto porcentual de cohorte FIJA y ventana terminal cerrada.

Reutiliza SIN MODIFICAR el inyector H08, los filtros H06 y las cohortes Vine.
La cohorte de referencia son los IDs OBSERVADOS en un baseline H08 validado;
NO se presume que sea toda la demanda programada en el archivo .rou.xml.
Selección determinista por ranking SHA256 anidado, con cuota exacta sobre
esa cohorte de referencia. No implica cuota exacta de vehículos intervenidos.

Unicamente una conexión TraCI: on_step() NO llama simulationStep().
Conducción naturalista/seguridad y escala temporal siguen NO CALIBRADAS.
"""
from __future__ import annotations
import argparse
from dataclasses import replace
import json
import math
from pathlib import Path
import shutil
import sys

import pandas as pd
import ntvc_vine_r_06_piloto_integracion_protegida as h06
import ntvc_vine_r_08_inyector_estres_porcentual as h08

VERSION = 'NTVC-Vine-R H08b Cohorte fija / horizonte auditado EXPERIMENTAL v1'
POST_GUARD_DECISIONS = frozenset({
    'probe_only', 'command_issued', 'total_command_quota',
    'step_command_quota', 'window_command_quota', 'vehicle_command_quota',
    'cooldown', 'safety_halt_collision_or_teleport',
})


def ordered_roster(vehicle_ids, seed):
    """IDs únicos, ranking estable; anidamiento exacto entre proporciones."""
    ids = [str(x) for x in vehicle_ids]
    if not ids or any(not x for x in ids):
        raise ValueError('Cohorte vacía o contiene IDs vacíos.')
    if len(set(ids)) != len(ids):
        raise ValueError('El baseline contiene IDs duplicados.')
    return tuple(sorted(ids, key=lambda vid: (h08.hash_score(seed, vid), vid)))


def select_exact(ranked, penetration):
    if not math.isfinite(penetration) or not 0 <= penetration <= 1:
        raise ValueError('Penetración fuera de [0,1].')
    # Redondeo half-up especificado, sin la regla bancaria de round().
    k = min(len(ranked), int(math.floor(len(ranked)*penetration + 0.5)))
    return frozenset(ranked[:k])


def read_reference(baseline_dir: Path, cfg_file: Path, seed: int,
                   steps: int, dt: float):
    """Verifica referencia sin tocar los archivos existentes."""
    baseline_dir = baseline_dir.resolve()
    mf = baseline_dir/'manifest_hito08.json'
    assignments = baseline_dir/'asignacion_hito08.csv'
    traffic = baseline_dir/'trafico_hito08.csv'
    for file in (mf, assignments, traffic):
        if not file.is_file():
            raise FileNotFoundError(f'Baseline incompleto: {file}')
    doc = json.loads(mf.read_text(encoding='utf-8'))
    meta = doc.get('metadata', {})
    if meta.get('mode') != 'baseline':
        raise RuntimeError('La referencia NO es un baseline H08.')
    if int(meta.get('seed', -1)) != int(seed):
        raise RuntimeError('Seed diferente de la referencia baseline.')
    if int(meta.get('n_steps', -1)) != int(steps):
        raise RuntimeError('Horizonte diferente del baseline.')
    if abs(float(doc.get('params', {}).get('step_length', -1)) - dt) > 1e-9:
        raise RuntimeError('Paso temporal diferente del baseline.')
    current_hashes = h06.sumo_input_hashes(cfg_file)
    if any(str(v) == 'UNRESOLVED' for v in current_hashes.values()):
        raise RuntimeError('El escenario tiene entradas sin resolver.')
    if current_hashes != doc.get('sumo_scenario_input_sha256'):
        raise RuntimeError('HASHES DEL ESCENARIO DIFIEREN DEL BASELINE: bloqueo.')
    seen_df = pd.read_csv(assignments, dtype={'vehicle_id': str},
                          keep_default_na=False)
    if 'vehicle_id' not in seen_df.columns:
        raise RuntimeError('Falta vehicle_id en la cohorte baseline.')
    ids = seen_df['vehicle_id'].tolist()
    ranked = ordered_roster(ids, seed)
    baseline_rows = pd.read_csv(traffic)
    if len(baseline_rows) != steps or (
        baseline_rows['step'].to_numpy() != list(range(steps))
    ).any():
        raise RuntimeError('CSV baseline no tiene secuencia completa.')
    return ranked, current_hashes, mf, assignments, doc


class FixedRosterInjector(h08.StressInjector):
    """Mismo núcleo H08; cambia solamente quién pertenece a la cohorte."""
    def __init__(self, config, kernel, groups, reference_ids, selected_ids):
        super().__init__(config, kernel, groups)
        self.reference_ids = frozenset(reference_ids)
        self.selected_ids = frozenset(selected_ids)
        if not self.selected_ids.issubset(self.reference_ids):
            raise ValueError('Seleccionados fuera de la cohorte de referencia.')

    def _membership(self, vid):
        return vid in self.selected_ids, h08.hash_score(self.cfg.seed, vid)

    def results(self):
        actions, fleet, assignment, meta = super().results()
        present = set(self.seen)
        sel_present = present & self.selected_ids
        meta.update(
            selection_method='exact_ranking_on_baseline_observed_cohort',
            reference_n_vehicles=len(self.reference_ids),
            reference_n_assigned=len(self.selected_ids),
            penetration_assigned_reference=(len(self.selected_ids) /
                len(self.reference_ids) if self.reference_ids else None),
            n_assigned_seen=len(sel_present),
            n_assigned_not_seen=len(self.selected_ids - present),
            n_unlisted_seen=len(present - self.reference_ids),
            # Acción viable ANTES de cuotas: incluye bloqueos por presupuesto.
            n_action_viable_before_quotas=sum(
                row.get('action_decision') in POST_GUARD_DECISIONS for row in self.rows),
            n_commands_confirmed=sum(
                bool(row.get('command_issued')) and bool(row.get('matched_t_plus_dt'))
                for row in self.rows),
        )
        return actions, fleet, assignment, meta


def self_test():
    ids = [str(i) for i in range(300)]
    ranked = ordered_roster(ids, seed=101)
    a, b, c = (select_exact(ranked, p) for p in (.15, .30, .50))
    assert len(a) == 45 and len(b) == 90 and len(c) == 150
    assert a < b < c
    assert ordered_roster(reversed(ids), 101) == ranked
    assert not select_exact(ranked, 0.)
    assert select_exact(ranked, 1.) == set(ids)
    try:
        ordered_roster(['a', 'a'], 101)
    except ValueError:
        pass
    else:
        raise AssertionError('No detecta duplicados.')
    # A t=300 el filtro original H08 exige t < end_time.
    assert not (0. <= 300. < 300.)
    assert 0. <= 299.5 < 300.
    print('SELF-TEST H08b OK: 45/90/150, anidamiento, IDs únicos, horizonte [0,300).')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--self-test', action='store_true')
    ap.add_argument('--mode', choices=('probe','active'), default='probe')
    ap.add_argument('--variant', choices=h06.VARIANTS, default='vine_student')
    ap.add_argument('--reference-baseline-dir', type=Path)
    ap.add_argument('--penetration', type=float, default=.15)
    ap.add_argument('--ack-active', default='')
    ap.add_argument('--ack-time-scale', default='')
    ap.add_argument('--sumo-config', type=Path)
    ap.add_argument('--sumo-binary', type=str)
    ap.add_argument('--data-dir', type=Path, default=h06.DEFAULT_DATA)
    ap.add_argument('--output', type=Path)
    ap.add_argument('--sumo-steps', type=int, default=600)
    ap.add_argument('--step-length', type=float, default=.5)
    ap.add_argument('--seed', type=int, default=101)
    ap.add_argument('--max-commands', type=int, default=500)
    ap.add_argument('--max-commands-per-step', type=int, default=2)
    ap.add_argument('--max-commands-per-window', type=int, default=20)
    ap.add_argument('--window-seconds', type=float, default=60.)
    ap.add_argument('--max-commands-per-vehicle', type=int, default=12)
    ap.add_argument('--cooldown-steps', type=int, default=8)
    ap.add_argument('--start-time', type=float, default=0.)
    ap.add_argument('--end-time', type=float, default=None,
                    help='Por defecto 600*0.5=300 s; ninguna acción en el último t=300.')
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not all((args.reference_baseline_dir, args.sumo_config, args.output)):
        ap.error('Faltan --reference-baseline-dir, --sumo-config o --output.')
    if args.mode == 'active' and (args.ack_active != h06.ACTIVE_ACK or
                                  args.ack_time_scale != h06.TIME_ACK):
        ap.error('Active requiere --ack-active EXPERIMENTAL_ONLY '
                 '--ack-time-scale NOT_CALIBRATED.')
    if args.sumo_steps < 5 or args.step_length <= 0:
        ap.error('Horizonte inválido.')
    horizon = args.sumo_steps*args.step_length
    end_time = horizon if args.end_time is None else min(args.end_time, horizon)
    cfg = h08.StressConfig(mode=args.mode, variant=args.variant, seed=args.seed,
          penetration=args.penetration, step_length=args.step_length,
          max_commands=args.max_commands,
          max_commands_per_step=args.max_commands_per_step,
          max_commands_per_window=args.max_commands_per_window,
          window_seconds=args.window_seconds,
          max_commands_per_vehicle=args.max_commands_per_vehicle,
          cooldown_steps=args.cooldown_steps, start_time=args.start_time,
          end_time=end_time)
    cfg.validate()
    cfg_file = args.sumo_config.resolve()
    if not cfg_file.is_file():
        raise FileNotFoundError(cfg_file)
    ranked, hashes, ref_manifest, ref_assignments, ref_doc = read_reference(
        args.reference_baseline_dir, cfg_file, args.seed,
        args.sumo_steps, args.step_length)
    selected = select_exact(ranked, cfg.penetration)
    out = args.output.resolve()
    approved = (h06.ROOT / 'resultados').resolve()
    if approved not in out.parents or out.exists():
        raise ValueError('Salida debe ser NUEVA y estar dentro de revision_naturalista/resultados.')
    kernel, groups, tables, n_pairs, ds_manifest = h08.load_frozen_cohorts(args.data_dir, cfg)
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
        raise RuntimeError('SUMO no está en PATH.')
    injector = FixedRosterInjector(cfg, kernel, groups, ranked, selected)
    out.mkdir(parents=True, exist_ok=False)
    cmd = [str(binary), '-c', str(cfg_file), '--seed', str(args.seed),
           '--output-prefix', str(out/'sumo_'), '--step-length', str(args.step_length)]
    print('COMANDO SUMO:', ' '.join(cmd), flush=True)
    print('H08b MODO:', cfg.mode, 'SELECCION:', len(selected), '/', len(ranked),
          'PENETRACION:', cfg.penetration, 'FIN EXCLUSIVO:', end_time, flush=True)
    print('AVISO: tiempo PoliDriving/SUMO no calibrado; solo prueba experimental.', flush=True)
    traci.start(cmd)
    try:
        for step in range(args.sumo_steps):
            traci.simulationStep()
            injector.on_step(traci, step)
            if traci.simulation.getMinExpectedNumber() == 0:
                break
    finally:
        traci.close()
    actions, fleet, assignment, meta = injector.results()
    if len(fleet) != args.sumo_steps or list(fleet['step']) != list(range(args.sumo_steps)):
        raise RuntimeError('Simulación incompleta; no crear manifiesto de éxito.')
    if meta['n_commands'] != meta['n_commands_confirmed'] or meta['remaining_pending']:
        raise RuntimeError('Comandos sin confirmar al finalizar: NO declarar éxito.')
    files = {'acciones_hito08.csv': actions, 'trafico_hito08.csv': fleet,
             'asignacion_hito08.csv': assignment}
    if tables is not None:
        files['familias_hito08_train.csv'] = tables
    for name, table in files.items():
        table.to_csv(out/name, index=False, float_format='%.12g')
    # Declaración de referencia completa SOLO si todos los observados pertenecen.
    meta['reference_covers_active_observed'] = meta['n_unlisted_seen'] == 0
    manifest = dict(version=VERSION, source_sumo_config=str(cfg_file),
        sumo_command=cmd, sumo_scenario_input_sha256=hashes,
        reference_baseline_manifest_sha256=h06.sha256(ref_manifest),
        reference_baseline_assignments_sha256=h06.sha256(ref_assignments),
        source_h06_sha256=h06.sha256(Path(h06.__file__).resolve()),
        source_h08_sha256=h06.sha256(Path(h08.__file__).resolve()),
        source_h03_sha256=h06.sha256(Path(h06.__file__).resolve().parent/
            'ntvc_vine_r_03_integracion_cinematica_sumo.py'),
        source_h04_sha256=h06.sha256(Path(h06.__file__).resolve().parent/
            'ntvc_vine_r_04_shadow_multivehiculo_rutas_corregidas.py'),
        frozen_hito01_manifest_sha256=(h06.sha256(args.data_dir/'manifest.json')
             if ds_manifest is not None else None),
        n_training_pairs=n_pairs, metadata=meta,
        params={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()
                if k not in ('ack_active','ack_time_scale')},
        effective_end_time=end_time,
        output_sha256={name:h06.sha256(out/name) for name in files},
        caveats=['Cohorte fija EXACTA sobre IDs vistos por baseline: NO rutas completas.',
          'La penetración de comandos puede ser menor por restricciones de seguridad.',
          'No implica seguridad general ni calibración temporal de Vine.',
          'Comparación causal requiere mantener semáforos/entorno RL equivalentes.',
          'Eventos de frenado se deben auditar en logs SUMO.'])
    (out/'manifest_hito08.json').write_text(json.dumps(
        manifest, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    print('RESUMEN HITO08b:', json.dumps(meta, ensure_ascii=False), flush=True)
    if not meta['reference_covers_active_observed']:
        print('ADVERTENCIA: IDs activos fuera de cohorte baseline:',
              meta['n_unlisted_seen'], flush=True)
    print('SALIDA:', out, flush=True)


if __name__ == '__main__':
    main()
