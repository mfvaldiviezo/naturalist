"""H12.12: contrato determinista del semáforo y observación de B1.

Solo biblioteca estándar. No importa SUMO, Gymnasium ni repositorio heredado.
El contrato es NUEVO e incompatible con los checkpoints PPO heredados.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import hashlib
import math
from pathlib import Path
import xml.etree.ElementTree as ET


class ContractError(ValueError):
    pass


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for block in iter(lambda: fh.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def require(condition, message):
    if not condition:
        raise ContractError(message)


@dataclass(frozen=True)
class Phase:
    index: int
    state: str
    duration_s: float

    @property
    def kind(self):
        if any(c in 'Gg' for c in self.state):
            return 'green'
        if any(c in 'yY' for c in self.state):
            return 'yellow'
        return 'all_red'


@dataclass(frozen=True)
class Geometry:
    tls_id: str
    source_xml_sha256: str
    program_id: str
    original_program_type: str
    lanes_in: tuple[str, ...]
    lane_out_by_in: tuple[tuple[str, tuple[str, ...]], ...]
    phases: tuple[Phase, ...]
    green_indices: tuple[int, ...]
    yellow_minimum_s: float
    # No se certifica ausencia de conflictos geométricos: reutiliza fases del net.xml.

    def as_json(self):
        d = asdict(self)
        d['actions'] = [dict(action=i, phase_index=p, state=self.phases[p].state)
                        for i, p in enumerate(self.green_indices)]
        return d


def read_geometry(net_xml, tls_id='B1', yellow_min_s=3.0):
    path = Path(net_xml).resolve(strict=True)
    require(path.suffix.lower() == '.xml', 'La red debe ser XML')
    # iterparse: compatible con redes grandes; bloquea DTD/entity externa con rechazo explícito
    with open(path, 'rb') as f:
        first = f.read(2048).upper()
    require(b'<!DOCTYPE' not in first and b'<!ENTITY' not in first,
            'DTD/ENTITY no admitidas en red SUMO')
    root = ET.parse(path).getroot()
    programs = [x for x in root.findall('tlLogic') if x.get('id') == tls_id]
    require(len(programs) == 1, f'{tls_id}: se requiere un único tlLogic (hallados {len(programs)})')
    program = programs[0]
    phases = tuple(Phase(i, p.get('state',''), float(p.get('duration','0')))
                   for i, p in enumerate(program.findall('phase')))
    require(len(phases) >= 4, 'Programa debe incluir verdes y transiciones')
    require(all(p.duration_s > 0 and math.isfinite(p.duration_s) for p in phases),
            'Fases deben tener duración positiva y finita')
    widths = {len(p.state) for p in phases}
    require(len(widths) == 1 and 0 not in widths, 'Longitud desigual de señales de fase')
    require(all(set(p.state) <= set('rRgGyYoO') for p in phases),
            'Símbolos de semáforo desconocidos')
    green = tuple(p.index for p in phases if p.kind == 'green')
    require(2 <= len(green) <= 4, 'Se requieren de 2 a 4 fases verdes distintas')
    transitions = [p for p in phases if p.index not in green]
    require(all(p.kind in ('yellow','all_red') for p in transitions), 'Interverdes no reconocidos')
    require(all(p.duration_s + 1e-9 >= yellow_min_s for p in transitions if p.kind == 'yellow'),
            'Fase amarilla más corta que el mínimo configurado')
    connections = [c for c in root.findall('connection') if c.get('tl') == tls_id]
    require(bool(connections), 'Sin conexiones del semáforo en red SUMO')
    input_to_output = {}
    seen_signal_idx = set()
    for c in connections:
        try:
            index = int(c.get('linkIndex', '-1'))
        except ValueError as exc:
            raise ContractError('linkIndex no entero') from exc
        require(0 <= index < len(phases[0].state), 'Índice de conexión fuera de las fases')
        require(index not in seen_signal_idx, 'linkIndex duplicado o ambiguo')
        seen_signal_idx.add(index)
        lane_in = f"{c.get('from')}_{c.get('fromLane')}"
        lane_out = f"{c.get('to')}_{c.get('toLane')}"
        require('None' not in lane_in+lane_out, 'Conexión sin carril completo')
        input_to_output.setdefault(lane_in, set()).add(lane_out)
    require(seen_signal_idx == set(range(len(phases[0].state))),
            'Señales y conexiones no cubren el mismo conjunto de índices')
    inputs = tuple(sorted(input_to_output))
    require(1 <= len(inputs) <= 4,
            f'Se requieren 1..4 carriles únicos para presión 4D: {len(inputs)}')
    # No repetir carriles ni inventar cero como carril físico: padding observación será explícito.
    outgoing = tuple((lane, tuple(sorted(input_to_output[lane]))) for lane in inputs)
    geometry = Geometry(tls_id, sha256_file(path), program.get('programID',''),
                        program.get('type',''), inputs, outgoing, phases, green,
                        float(yellow_min_s))
    for source in green:
        for target in green:
            if source != target:
                transition_path(geometry, source, target)
    return geometry


def transition_path(geometry: Geometry, current: int, target: int):
    require(current in geometry.green_indices and target in geometry.green_indices,
            'Los extremos de la transición deben ser verdes')
    require(current != target, 'No existe transición hacia la misma fase')
    out = []
    n = len(geometry.phases)
    for offset in range(1,n+1):
        idx=(current+offset)%n
        if idx == target:
            break
        require(idx not in geometry.green_indices,
                'Otra fase verde intermedia: no se autoriza saltarla')
        out.append(idx)
    else:
        raise ContractError('Destino de transición no encontrado')
    yellows = [geometry.phases[i] for i in out if geometry.phases[i].kind == 'yellow']
    require(bool(yellows), f'{current}->{target}: sin ámbar intermedio')
    require(sum(x.duration_s for x in yellows) >= geometry.yellow_minimum_s,
            'Duración amarilla total insuficiente')
    # Nunca generar estados inéditos; reproducir el programa SUMO oficial fase a fase.
    return tuple(out + [target])


class PhaseScheduler:
    """Autómata independiente del simulador, estados emitidos solo de net.xml.

    Una acción diferente solicita cambio si el verde actual cumple min_green.
    Las peticiones durante un interverde se ignoran; se completan fases intermedias.
    advance(dt, action) devuelve estado a mostrar DURANTE el microtick actual.
    """
    def __init__(self, geometry: Geometry, min_green_s=10.0, initial_phase=None):
        self.geometry = geometry
        self.min_green_s = float(min_green_s)
        require(math.isfinite(self.min_green_s) and self.min_green_s >= 1,
                'Min green debe ser >=1s')
        self.stage = geometry.green_indices[0] if initial_phase is None else initial_phase
        require(self.stage in geometry.green_indices, 'Fase inicial no verde')
        self.green_phase = self.stage
        self.stage_elapsed = 0.0
        self.green_elapsed = 0.0
        self.path = []
        self.transitions = []

    @property
    def state(self):
        return self.geometry.phases[self.stage].state

    @property
    def kind(self):
        return self.geometry.phases[self.stage].kind

    def advance(self, dt, action):
        require(math.isfinite(dt) and 0 < dt <= 1.0, 'Microtick debe ser >0 y <=1s')
        require(type(action) is int and 0 <= action < len(self.geometry.green_indices),
                'Acción discreta fuera de las fases verdes')
        target = self.geometry.green_indices[action]
        if self.path and self.stage_elapsed + 1e-8 >= self.geometry.phases[self.stage].duration_s:
            self.stage = self.path.pop(0)
            self.stage_elapsed = 0.0
            self.transitions.append(('enter', self.stage))
            if self.stage in self.geometry.green_indices:
                self.green_phase = self.stage
                self.green_elapsed = 0.0
        if not self.path and self.stage in self.geometry.green_indices and target != self.stage and self.green_elapsed + 1e-9 >= self.min_green_s:
            self.path = list(transition_path(self.geometry, self.stage, target))
            self.stage = self.path.pop(0)
            self.stage_elapsed = 0.0
            self.transitions.append(('enter', self.stage))
        self.stage_elapsed += dt
        if self.stage in self.geometry.green_indices:
            self.green_elapsed += dt
        return self.state


def observation_34(lane_inputs, counts, halts, waits, downstream, stage, age_s,
                   green_indices, min_green_s, pressure_cap=50.0,
                   max_queue=50.0, max_wait=300.0):
    """q12 + w12 + p4 + phi4 + tau2; todas dimensiones [0,1], sin carriles repetidos.

    pressure[i] = (N_in(i) - avg(N_out in controlled links(i)))/(2*cap)+0.5.
    El cero de presión física corresponde a 0.5; las salidas son promedio y no suma.
    """
    require(len(lane_inputs) <= 4 and len(set(lane_inputs)) == len(lane_inputs),
            'Carriles no únicos o >4')
    def read_value(d, lane):
        v = float(d[lane])
        require(math.isfinite(v) and v >= 0, f'Lectura negativa/no finita: {lane}')
        return v
    qs = [min(read_value(halts, lane)/max_queue,1.0) for lane in lane_inputs]
    ws = [min(read_value(waits, lane)/max_wait,1.0) for lane in lane_inputs]
    q = qs + [0.0]*(12-len(qs))
    w = ws + [0.0]*(12-len(ws))
    p=[]
    for lane in lane_inputs:
        destination_lanes = downstream[lane]
        require(bool(destination_lanes),'Sin salida para carril '+lane)
        out_avg = sum(read_value(counts,l) for l in destination_lanes)/len(destination_lanes)
        pressure = read_value(counts,lane) - out_avg
        p.append(min(1.0,max(0.0,0.5+pressure/(2*pressure_cap))))
    p += [0.5]*(4-len(p))  # Neutral de presión en carriles no existentes
    phi = [0.0]*4
    if stage in green_indices:
        phi[green_indices.index(stage)] = 1.0
    require(math.isfinite(age_s) and age_s >= 0, 'Edad no válida')
    tau = [min(age_s/120.0, 1.0), min(age_s/min_green_s,1.0)]
    data = q+w+p+phi+tau
    require(len(data)==34 and all(0 <=x <=1 and math.isfinite(x) for x in data),
            'Observación inconsistente con Box')
    return data


def gini(values):
    if not values:
        return 0.0
    require(all(math.isfinite(float(x)) and float(x) >=0 for x in values), 'Gini espera inválida')
    total=sum(values)
    if total <= 1e-12:
        return 0.0
    n=len(values)
    return sum(abs(a-b) for a in values for b in values)/(2*n*total)


def cvar95(values):
    if not values:
        return 0.0
    vals=sorted(float(x) for x in values)
    require(all(math.isfinite(v) and v>=0 for v in vals), 'CVaR espera inválida')
    # CVaR discreto de cola superior: media del ceil(5% de carriles peores).
    import math as _math
    k=max(1,_math.ceil(0.05*len(vals)))
    return sum(vals[-k:])/k


def reward_components(waits, weights=(0.4,0.3,0.3), wait_cap=300.0):
    vals=list(waits)
    require(bool(vals), 'Sin carriles reales en recompensa')
    require(all(math.isfinite(v) and v>=0 for v in vals), 'Espera no válida')
    a=min(sum(vals)/(len(vals)*wait_cap),1.0)
    b=gini(vals)
    c=min(cvar95(vals)/wait_cap,1.0)
    require(abs(sum(weights)-1)<1e-9 and all(v>=0 for v in weights), 'Pesos de recompensa no válidos')
    return {'delay_norm': a,'gini': b,'cvar95_norm': c,
            'reward': -(weights[0]*a+weights[1]*b+weights[2]*c)}
