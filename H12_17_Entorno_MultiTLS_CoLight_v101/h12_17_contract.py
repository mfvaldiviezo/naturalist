"""H12.17 — contratos verificables Hangzhou multi-TLS; solo stdlib.

NO implementa ni modifica CoLight. Reutiliza exclusivamente la semántica
H12.12 de los vectores 34D mediante imports explícitos en el entorno/runner.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
import math
import xml.etree.ElementTree as ET

SCHEMA = 'H12_17_HZ12_MULTI_TLS_GRAPH_GREEN2_V100'
EXPECTED_TLS = ('A1','A2','B0','B1','B2','B3','C0','C1','C2','C3','D1','D2')
EXPECTED_NET_SHA = '2590ca460dafb57a4c608f4fe1ad9de072068a5b2ef0ea487f617296d8c627f6'
EXPECTED_ROUTE_SHA = 'a78363c99e1a6eab33028c3a36c82dcb66129adf8e73141612b9e7b2358f1369'

class ContractError(ValueError):
    pass

def require(condition,msg):
    if not condition:
        raise ContractError(msg)

def sha256_file(p):
    h=hashlib.sha256()
    with open(p,'rb') as fd:
        for block in iter(lambda:fd.read(1<<20),b''):
            h.update(block)
    return h.hexdigest()

def read_safe_xml(p):
    p=Path(p).resolve(strict=True)
    # fail closed ante DTD o entidad en cualquier parte del archivo
    with p.open('rb') as f:
        data=f.read()
    upper=data.upper()
    require(b'<!DOCTYPE' not in upper and b'<!ENTITY' not in upper,
            'XML con DOCTYPE/ENTITY prohibido')
    try:
        return ET.fromstring(data)
    except ET.ParseError as e:
        raise ContractError('XML no válido: '+str(e)) from e

@dataclass(frozen=True)
class Phase:
    index:int
    state:str
    duration_s:float
    @property
    def kind(self):
        # CRÍTICO: en A1/A2/etc un amarillo conserva G en links no conflictivos.
        # Debe tener prioridad Y/y, no G/g.
        if any(c in 'yY' for c in self.state): return 'yellow'
        if any(c in 'Gg' for c in self.state): return 'green'
        return 'all_red'

@dataclass(frozen=True)
class Geometry:
    tls_id:str
    source_xml_sha256:str
    program_id:str
    original_program_type:str
    lanes_in:tuple[str,...]
    lane_out_by_in:tuple[tuple[str,tuple[str,...]],...]
    phases:tuple[Phase,...]
    green_indices:tuple[int,...]
    yellow_minimum_s:float
    def as_json(self):
        d=asdict(self)
        d['lanes_in']=list(self.lanes_in)
        d['green_indices']=list(self.green_indices)
        d['lane_out_by_in']=[[a,list(b)] for a,b in self.lane_out_by_in]
        d['action_to_phase']={str(i):p for i,p in enumerate(self.green_indices)}
        return d

@dataclass(frozen=True)
class Network:
    net_sha256:str
    node_ids:tuple[str,...]
    geometries:tuple[Geometry,...]
    directed_edges:tuple[tuple[str,str],...]
    def as_json(self):
        pos={v:i for i,v in enumerate(self.node_ids)}
        edges=[[pos[a],pos[b]] for a,b in self.directed_edges]
        adj={node:sorted({b for a,b in self.directed_edges if a==node}) for node in self.node_ids}
        incoming={node:sorted({a for a,b in self.directed_edges if b==node}) for node in self.node_ids}
        return dict(node_order=list(self.node_ids),node_to_index=pos,
                    graph_directed_edge_index=[[e[0] for e in edges],[e[1] for e in edges]],
                    graph_directed_edges=[list(x) for x in self.directed_edges],
                    directed_out_neighbors=adj,directed_in_neighbors=incoming,
                    graph_has_self_loops=False,required_colight_self_loop_policy='DEFERRED_TO_MODEL',
                    geometries={g.tls_id:g.as_json() for g in self.geometries},
                    net_sha256=self.net_sha256)

def transition_path(geo,current,target):
    require(current in geo.green_indices and target in geo.green_indices and current!=target,
            'Transición debe conectar dos verdes diferentes')
    n=len(geo.phases); mids=[]
    for offset in range(1,n+1):
        j=(current+offset)%n
        if j==target: break
        require(geo.phases[j].kind!='green','No saltar verde intermedio')
        mids.append(j)
    else: raise ContractError('No se alcanzó la fase objetivo')
    ys=[geo.phases[k] for k in mids if geo.phases[k].kind=='yellow']
    require(ys and sum(p.duration_s for p in ys)+1e-9>=geo.yellow_minimum_s,
            f'{geo.tls_id} {current}->{target}: interverde insuficiente')
    # No crear verde nuevo DURANTE el amarillo. Solo sobreviven verdes ya activos.
    src=geo.phases[current].state
    for p in (geo.phases[k] for k in mids):
        for k,c in enumerate(p.state):
            if c in 'Gg':
                require(src[k] in 'Gg',f'{geo.tls_id}: verde nuevo durante amarillo en link {k}')
    return tuple(mids+[target])

def parse_network(net_xml,require_hangzhou=True):
    root=read_safe_xml(net_xml)
    require(root.tag=='net','Archivo no es una red SUMO')
    sha=sha256_file(net_xml)
    if require_hangzhou:
        require(sha==EXPECTED_NET_SHA,'SHA-256 red distinta de Hangzhou H12.12 fijada')
    programs=root.findall('tlLogic')
    tlsids=tuple(sorted(p.get('id','') for p in programs))
    require(len(tlsids)>=2 and len(set(tlsids))==len(tlsids),'TLS ausentes o duplicados')
    if require_hangzhou:
        require(tlsids==EXPECTED_TLS,f'Lista TLS distinta de 12 Hangzhou: {tlsids}')
    links={id_:[] for id_ in tlsids}
    for c in root.findall('connection'):
        tid=c.get('tl')
        if tid in links: links[tid].append(c)
    geos=[]
    for program in sorted(programs,key=lambda x:x.get('id','')):
        tid=program.get('id')
        phases=tuple(Phase(i,p.get('state',''),float(p.get('duration','0')))
                    for i,p in enumerate(program.findall('phase')))
        require(len(phases)==4,f'{tid}: H12.17 requiere programa de 4 etapas')
        w={len(p.state) for p in phases}
        require(len(w)==1 and 0 not in w,f'{tid}: anchos de estados inconsistentes')
        require(all(p.duration_s>0 and math.isfinite(p.duration_s) and set(p.state)<=set('rRgGyYoO') for p in phases),
                f'{tid}: estado/duración no válida')
        greens=tuple(p.index for p in phases if p.kind=='green')
        yellows=tuple(p.index for p in phases if p.kind=='yellow')
        require(greens==(0,2) and yellows==(1,3),f'{tid}: verdes/amarillos no homologables {greens}/{yellows}')
        require(all(phases[i].duration_s+1e-9>=3.0 for i in yellows),f'{tid}: amarillo <3s')
        require(links[tid],f'{tid}: sin conexiones')
        maplinks={}; indices=set()
        for c in links[tid]:
            try: idx=int(c.get('linkIndex','-1'))
            except ValueError as e: raise ContractError('linkIndex no entero') from e
            require(idx not in indices and 0<=idx<len(phases[0].state),f'{tid}: linkIndex inválido/duplicado')
            indices.add(idx)
            lane_in=f"{c.get('from')}_{c.get('fromLane')}"
            lane_out=f"{c.get('to')}_{c.get('toLane')}"
            require('None' not in lane_in+lane_out,f'{tid}: conexión incompleta')
            maplinks.setdefault(lane_in,set()).add(lane_out)
        require(indices==set(range(len(phases[0].state))),f'{tid}: links no cubren estados TLS')
        inbound=tuple(sorted(maplinks))
        require(1<=len(inbound)<=4,f'{tid}: n carriles fuera de 1..4')
        geo=Geometry(tid,sha,program.get('programID',''),program.get('type',''),
                     inbound,tuple((lane,tuple(sorted(maplinks[lane]))) for lane in inbound),
                     phases,greens,3.0)
        transition_path(geo,0,2)
        transition_path(geo,2,0)
        geos.append(geo)
    node_set=set(tlsids)
    graph=set()
    for edge in root.findall('edge'):
        src,dst=edge.get('from'),edge.get('to')
        if src in node_set and dst in node_set and src!=dst:
            graph.add((src,dst))
    require(bool(graph),'No se identificaron conexiones viales entre TLS')
    if require_hangzhou:
        require(len(graph)==32,f'Hangzhou H12.12 debe tener 32 aristas dirigidas; detectadas {len(graph)}')
    for name in tlsids:
        require(any(name in edge for edge in graph),f'{name}: semáforo aislado')
    # Conectividad débil obligatoria, no exigir conectividad fuerte en otras redes.
    reached={tlsids[0]}
    while True:
        new=reached|{b for a,b in graph if a in reached}|{a for a,b in graph if b in reached}
        if new==reached:break
        reached=new
    require(reached==node_set,'Grafo desconectado: no habilitar atención CoLight')
    return Network(sha,tlsids,tuple(geos),tuple(sorted(graph)))

class PhaseScheduler:
    """Transiciones seguras con estados exactos del net.xml. tick <= 1 s.

    Política durante amarillo: ignorar peticiones nuevas; completar interverde.
    El verde mínimo se aplica al verde actual DESDE su entrada real.
    """
    def __init__(self,geo,min_green_s=10.0,initial_phase=None):
        self.geo=geo
        self.min_green_s=float(min_green_s)
        require(math.isfinite(self.min_green_s) and self.min_green_s>=5.0,
                'min_green_s debe ser >=5 s')
        self.stage=geo.green_indices[0] if initial_phase is None else int(initial_phase)
        require(self.stage in geo.green_indices,'Fase inicial no verde')
        self.stage_elapsed=0.0
        self.green_elapsed=0.0
        self.path=[]
        self.transitions=[]
    @property
    def state(self): return self.geo.phases[self.stage].state
    @property
    def kind(self): return self.geo.phases[self.stage].kind
    def advance(self,dt,action):
        require(math.isfinite(dt) and 0<dt<=1,'dt fuera de rango')
        require(type(action) is int and 0<=action<len(self.geo.green_indices), 'Acción fuera de verdes')
        target=self.geo.green_indices[action]
        if self.path and self.stage_elapsed+1e-8>=self.geo.phases[self.stage].duration_s:
            self.stage=self.path.pop(0)
            self.stage_elapsed=0.0
            self.transitions.append(('enter',self.stage))
            if self.stage in self.geo.green_indices:self.green_elapsed=0.0
        if (not self.path and self.stage in self.geo.green_indices and
            target!=self.stage and self.green_elapsed+1e-8>=self.min_green_s):
            self.path=list(transition_path(self.geo,self.stage,target))
            self.stage=self.path.pop(0)
            self.stage_elapsed=0.0
            self.transitions.append(('enter',self.stage))
        self.stage_elapsed+=dt
        if self.kind=='green':self.green_elapsed+=dt
        return self.state

def validate_route(route_file, expected_sha=EXPECTED_ROUTE_SHA):
    root=read_safe_xml(route_file)
    require(root.tag=='routes','Rutas deben tener raíz <routes>')
    sha=sha256_file(route_file)
    if expected_sha:require(sha==expected_sha,'SHA rutas no coincide con H12.12')
    return sha
