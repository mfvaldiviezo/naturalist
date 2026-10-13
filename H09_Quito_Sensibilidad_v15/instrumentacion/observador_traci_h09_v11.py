#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H09 v1.5: adaptador de SOLO LECTURA para EventObserver 1.1.

Se usa vía --instrument-dir del runner H09 v1.2 SIN modificar dicho runner.
Registra una exposición a r/y/g por episodio y color, y una oportunidad
operativa si speed >= 1 m/s dentro de 30 m del TLS. Una oportunidad es
una PROXY cinemática, no una decisión ni un denominador comparable con Quito.
Asocia cruces al episodio de aproximación cuando hay traza observable.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from pathlib import Path
import importlib.util
import math

src=Path(__file__).resolve().parents[2]/'H09_Quito_Instrumentacion_v11'/'scripts'/'observador_traci_h09_v11.py'
if not src.is_file():
    raise FileNotFoundError('Se requiere el observador validado v1.1: '+str(src))
spec=importlib.util.spec_from_file_location('_h09_original_v11',str(src))
_mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)
FIELDS=_mod.FIELDS
fmt_phase=_mod.fmt_phase

class EventObserver(_mod.EventObserver):
    """Extensión de observación que no escribe comandos TraCI."""
    def __init__(self,*args,opportunity_radius_m=30.0,moving_threshold_mps=1.0,**kwargs):
        super().__init__(*args,**kwargs)
        self.opportunity_radius_m=float(opportunity_radius_m)
        self.moving_threshold_mps=float(moving_threshold_mps)
        if not 0<self.opportunity_radius_m<=100 or not 0<self.moving_threshold_mps<=20:
            raise ValueError('Umbrales instrumentales inválidos')
        self._visits=defaultdict(int)
        self._active={}
        self._seen_exposure=set()
        self._seen_moving=set()
        self._links=Counter()

    def _make_row(self,vid,tls,episode,etype,phase,time_s,dist,speed,quality='observed_snapshot',reason=''):
        return dict(run_id=self.run_id,seed=self.seed,vehicle_id=vid,
            site_id=tls,passage_id=f'{episode}|{etype}|{phase}',
            event_type=etype,signal_state=phase,classification_quality=quality,
            speed_mps=speed,limit_mps='',measurement_id=episode,time_s=time_s,
            observation_method='getNextTLS_snapshot_episode_30m',
            distance_prev_m=round(dist,5) if dist is not None else '',
            phase_prev=phase,phase_current=phase,lane_prev='',lane_current='',
            reason=reason)

    def observe(self,traci):
        # La lógica de cruces oficial v1.1 se mantiene INTACTA.
        old_active=dict(self._active)
        start=len(self.rows)
        super().observe(traci)
        now=self.prev_time
        current={}
        # Uno por vehículo/TLS/linkIndex; no por cada paso detenido.
        for vid,snapshot in self.prev.items():
            for tls,(idx,dist,state) in snapshot['tls'].items():
                if not math.isfinite(dist) or not 0<=dist<=self.opportunity_radius_m:continue
                key=(vid,tls,idx)
                if key in old_active:
                    episode=old_active[key]
                else:
                    self._visits[key]+=1
                    episode=f'h09ep|{vid}|{tls}|{idx}|{self._visits[key]}'
                current[key]=episode
                phase=fmt_phase(state)
                if phase not in ('red','yellow','green'):continue
                xkey=(episode,phase)
                if xkey not in self._seen_exposure:
                    self._seen_exposure.add(xkey)
                    self.rows.append(self._make_row(vid,tls,episode,'tls_phase_exposure',phase,
                         now,dist,snapshot['speed'],reason='PHASE_EXPOSURE_ONE_PER_EPISODE_AND_COLOR'))
                if snapshot['speed']>=self.moving_threshold_mps and xkey not in self._seen_moving:
                    self._seen_moving.add(xkey)
                    self.rows.append(self._make_row(vid,tls,episode,'tls_moving_opportunity',phase,
                         now,dist,snapshot['speed'],reason='MOVING_PROXY_NOT_INFRINGEMENT_OPPORTUNITY_PROBABILITY'))
        # Cruce emitido por v1.1: vincularlo al episodio ANTERIOR, no inventar uno.
        for crossing in self.rows[start:]:
            if crossing['event_type']!='stopline':continue
            vid=str(crossing['vehicle_id']);tls=str(crossing['site_id'])
            matches=[(k,e) for k,e in old_active.items() if k[0]==vid and k[1]==tls]
            episode=matches[0][1] if len(matches)==1 else ''
            self._links['linked' if episode else 'unlinked']+=1
            record=dict(crossing)
            record.update(event_type='tls_crossing_link',measurement_id=episode,
                          observation_method='join_stopline_to_active_tls_episode',
                          reason='LINKED_PRE_CROSSING_EPISODE' if episode else 'NO_EPISODE_IN_30M_PREVIOUS_FRAME')
            self.rows.append(record)
        self._active=current

    def stats(self):
        base=super().stats()
        ctr=Counter((r['event_type'],r['signal_state']) for r in self.rows)
        base['instrumentation_v15']={
          'phase_exposures':{p:ctr[('tls_phase_exposure',p)] for p in ('red','yellow','green')},
          'moving_opportunities':{p:ctr[('tls_moving_opportunity',p)] for p in ('red','yellow','green')},
          'crossing_episode_links':dict(self._links),
          'opportunity_radius_m':self.opportunity_radius_m,
          'moving_threshold_mps':self.moving_threshold_mps,
          'status':'OPERATIONAL_MOVING_PROXY_NOT_QUITO_CONDITIONAL_PROBABILITY'}
        return base
