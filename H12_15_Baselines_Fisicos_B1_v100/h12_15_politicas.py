"""H12.15: proyección explícita de Fixed y MaxPressure RESCO sobre B1 físico.

NO carga agentes originales ni acredita su equivalencia completa: RESCO define
8 pares de fase para Hangzhou, mientras que el net.xml bajo H12.12 tiene 2 verdes.
Se admiten SOLO pares originales (0,4), cuando coinciden geométricamente con
los verdes físicos (0,2). Los 6 pares restantes NO tienen fase independiente.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
from pathlib import Path
import xml.etree.ElementTree as ET

class PhysicalAdapterError(ValueError):
    pass


def check(ok, message):
    if not ok:
        raise PhysicalAdapterError(message)


@dataclass(frozen=True)
class Direction:
    name: str
    inbound: tuple[str, ...]
    downstream: tuple[str, ...]


@dataclass(frozen=True)
class PhysicalProjection:
    physical_green_phases: tuple[int,...]
    original_resco_pair_indices: tuple[int,...]
    original_resco_pairs: tuple[tuple[str,str],...]
    grouped_inbound: tuple[tuple[str,...],...]
    directions: tuple[tuple[Direction,...],...]
    original_resco_action_count: int
    original_resco_fixed_timings: tuple[int,...]
    fixed_target_green_s: float

    def document(self):
        return {
            'green_phases':list(self.physical_green_phases),
            'resco_original_action_count':self.original_resco_action_count,
            'resco_selected_original_pair_indices':list(self.original_resco_pair_indices),
            'resco_selected_pairs':[list(p) for p in self.original_resco_pairs],
            'inbound_physical_groups':[list(g) for g in self.grouped_inbound],
            'pressure_directions':[
                [{'code':d.name,'inbound':list(d.inbound),'downstream':list(d.downstream)} for d in group]
                for group in self.directions],
            'original_fixed_timings_resco_8':list(self.original_resco_fixed_timings),
            'fixed_target_green_s':self.fixed_target_green_s,
            'identity':'B1 physical projections; NOT original 8-action RESCO SOTA reproduced',
            'pressure_proxy':'TraCI instantaneous halting counts for RESCO lane.queued; differs from persistent vehicle queued flag',
        }


def build_projection(geometry, xml_path, signal_yaml_doc):
    """Comprueba la proyección 8->2 contra las conexiones reales del net.xml.

    No remapea arbitrariamente acciones no realizables: FALLA si los pares
    0 y 4 ya no cubren los verdes físicos completos de Hangzhou B1.
    """
    check(geometry.tls_id=='B1' and tuple(geometry.green_indices)==(0,2),
          'Solo Hangzhou B1 con verdes físicos 0 y 2')
    check(len(geometry.lanes_in)==4, 'B1 debe tener exactamente cuatro carriles reales')
    check(isinstance(signal_yaml_doc,dict),'signal.yaml RESCO inválido')
    scenario=signal_yaml_doc.get('hangzhou')
    check(isinstance(scenario,dict),'Falta perfil RESCO hangzhou')
    raw_pairs=scenario.get('phase_pairs')
    check(isinstance(raw_pairs,list) and len(raw_pairs)==8,'RESCO debe declarar ocho pares originales')
    selected=(0,4)
    expected=(('S-S','N-N'),('W-W','E-E'))
    check(tuple(tuple(raw_pairs[i]) for i in selected)==expected,
          'RESCO cambió phase_pairs[0]/phase_pairs[4]; no autoadaptar')
    b1=scenario.get('B1')
    check(isinstance(b1,dict) and isinstance(b1.get('lane_sets'),dict),'Falta lane_sets B1 de RESCO')
    timing=b1.get('fixed_timings')
    check(isinstance(timing,list) and len(timing)==8 and all(isinstance(v,int) for v in timing),
          'FIXED RESCO no mantiene plan original de ocho entradas')
    # En net.xml cada índice de enlace tiene UNA entrada, asociada al estado de fase.
    root=ET.parse(xml_path).getroot()
    conns=[c for c in root.findall('connection') if c.get('tl')=='B1']
    check(len(conns)==len(geometry.phases[0].state),'Cantidad de conexiones B1 incompatible')
    indices={lane:[] for lane in geometry.lanes_in}
    for c in conns:
        lane=f"{c.get('from')}_{c.get('fromLane')}"
        check(lane in indices, 'Conexión sin carril físico inventariado')
        indices[lane].append(int(c.get('linkIndex')))
    check(all(indices.values()),'Falta conexión de algún carril B1')
    by_phase=[]
    for phase_index in geometry.green_indices:
        phase_state=geometry.phases[phase_index].state
        green=set()
        for lane, idxs in indices.items():
            colors={phase_state[i] for i in idxs}
            check(not (any(c in 'Gg' for c in colors) and any(c in 'rR' for c in colors)),
                  'Carril tiene movimientos mixtos verde/rojo; no se puede proyectar por carril')
            if any(c in 'Gg' for c in colors):green.add(lane)
        by_phase.append(green)
    check(by_phase[0].isdisjoint(by_phase[1]) and
          by_phase[0]|by_phase[1]==set(geometry.lanes_in),
          'La partición de carriles físicos por verde cambió')
    groups=[];dirs=[]
    down=b1.get('downstream')
    check(isinstance(down,dict),'Falta downstream RESCO B1')
    for action,pair in enumerate(expected):
        dr=[];grp=set()
        for code in pair:
            incoming=tuple(sorted(set(b1['lane_sets'].get(code,[]))))
            check(incoming, f'Dirección RESCO {code} sin entrada')
            check(set(incoming)<=set(geometry.lanes_in),'Carril RESCO fuera de B1: '+code)
            grp.update(incoming)
            d=code.split('-')[1]
            neighbor_name=down.get(d)
            outgoing=set()
            if neighbor_name is not None:
                neighbor=scenario.get(neighbor_name)
                check(isinstance(neighbor,dict) and isinstance(neighbor.get('lane_sets'),dict),
                      'Vecino RESCO ausente: '+str(neighbor_name))
                for neighbor_code,lanes in neighbor['lane_sets'].items():
                    if neighbor_code.split('-')[0]==d:outgoing.update(lanes)
                check(outgoing,'Vecino RESCO sin carriles downstream para '+code)
            dr.append(Direction(code,incoming,tuple(sorted(outgoing))))
        check(grp==by_phase[action],
              f'Par RESCO #{selected[action]} no equivale a verde físico #{geometry.green_indices[action]}')
        groups.append(tuple(sorted(grp)));dirs.append(tuple(dr))
    check(sum(len(g) for g in groups)==4,'No se pudo particionar cuatro carriles')
    # 42 s de duración original de cada VERDE físico del XML, NO el plan Fixed RESCO 8 fases.
    green_durs=tuple(geometry.phases[p].duration_s for p in geometry.green_indices)
    check(abs(green_durs[0]-green_durs[1])<1e-8 and green_durs[0]>0,
          'Verdes no simétricos; plan FIXED_B1 requiere revisión')
    return PhysicalProjection(tuple(geometry.green_indices),selected,expected,
                              tuple(groups),tuple(dirs),len(raw_pairs),tuple(timing),
                              float(green_durs[0]))


def score_directions(projection, lane_halts):
    """Analogía local a RESCO states.mplight + MaxAgent(WaveAgent).

    Reserva exacta de direcciones: sum(incoming queued)-sum(downstream queued).
    Referencia usa Lane.queued que mantiene estado vehicular persistente; aquí se
    mide detención instantánea via SUMO. Los nombres evitan afirmar equivalencia.
    """
    def q(lane):
        check(lane in lane_halts,'No existe lectura de carril requerido: '+lane)
        value=float(lane_halts[lane]);check(math.isfinite(value) and value>=0,'Lectura inválida: '+lane)
        return value
    return tuple(sum(sum(q(l) for l in d.inbound)-sum(q(l) for l in d.downstream)
                     for d in group) for group in projection.directions)


def maxpressure_action(projection,lane_halts):
    values=score_directions(projection,lane_halts)
    # RESCO WaveAgent emplea np.argmax: ante empate gana la primera acción.
    idx=max(range(len(values)),key=lambda i:values[i])
    return idx,values


def fixed_action(projection,scheduler):
    """Baseline nuevo: duración verde objetivo tomada del net.xml (42s).

    Su resolución real es de 5s por decisión; puede pedir cambio más tarde.
    No equivale al Fixed RESCO original de 8 slots/phase_pairs.
    """
    check(scheduler is not None,'Scheduler de H12.12 no iniciado')
    greens=projection.physical_green_phases
    check(scheduler.green_phase in greens,'Fase verde previa inválida')
    active=greens.index(scheduler.green_phase)
    if scheduler.path: return 1-active
    check(math.isfinite(scheduler.green_elapsed) and scheduler.green_elapsed>=0,
          'Tiempo verde inválido')
    return 1-active if scheduler.green_elapsed+1e-8>=projection.fixed_target_green_s else active
