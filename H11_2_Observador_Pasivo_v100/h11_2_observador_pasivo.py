#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H11.2: observador PASIVO TraCI; cero cambios de estado SUMO.

No llama simulationStep/start/close, no usa setters, ni toca estado aleatorio.
Cruces son proxies y detenciones internas NO son gridlock confirmado.
"""
from __future__ import annotations
import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

VERSION = "H11.2-observador-pasivo-v1.0.0"
TRAJ_COLS = ["step", "time_s", "dt_s", "vehicle_id", "cohort", "vtype", "road_id", "lane_id", "internal_lane", "lane_pos_m", "x_m", "y_m", "speed_m_s", "speed_kmh", "accel_m_s2", "jerk_observed_m_s3", "posted_lane_limit_m_s", "allowed_speed_m_s", "above_posted_lane_limit", "leader_id", "gap_m", "leader_speed_m_s", "closing_speed_m_s", "headway_s", "ttc_s", "tls_id", "tls_link_index", "tls_state", "tls_distance_m", "required_stop_decel_m_s2", "next_lane_id", "next_lane_halted", "next_lane_n_vehicles"]
TLS_COLS = ["step", "time_s", "vehicle_id", "cohort", "event_kind", "tls_id", "link_index", "episode_id", "lane_before", "lane_after", "road_before", "road_after", "state_previous", "state_current", "distance_previous_m", "distance_current_m", "speed_previous_m_s", "required_stop_decel_m_s2", "color_label", "quality", "notes"]
INT_COLS = ["vehicle_id", "cohort", "road_id", "lane_id", "start_s", "end_s", "duration_s", "min_speed_m_s", "next_lane_id", "next_lane_halted", "next_lane_n_vehicles", "event_kind", "gridlock_confirmed", "evidence_quality", "censored_end"]
SAFE_COLS = ["step", "time_s", "colliding_vehicles_count", "colliding_vehicle_ids", "teleport_start_count", "teleport_start_ids", "emergency_stop_count", "emergency_stop_ids", "telemetry_errors"]


def _num(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def _color(state):
    s = str(state).lower() if state is not None else ""
    return "red" if s == "r" else "yellow" if s == "y" else "green" if s == "g" else "unknown"


def load_ids(path):
    """Accept text with one id per line or CSV with vehicle_id/id column."""
    if not path:
        return set()
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8-sig", newline="") as fh:
        first = fh.readline()
        fh.seek(0)
        if ',' in first or ';' in first:
            delim = ';' if ';' in first and ',' not in first else ','
            reader = csv.DictReader(fh, delimiter=delim)
            fld = next((f for f in ("vehicle_id", "id", "veh_id") if f in (reader.fieldnames or [])), None)
            if not fld:
                raise ValueError(f"CSV de cohortes sin vehicle_id/id/veh_id: {path}")
            return {str(r[fld]).strip() for r in reader if str(r.get(fld, '')).strip()}
        skip_header = first.strip().lower() in ("vehicle_id", "id", "veh_id")
        return {x.strip() for i, x in enumerate(fh) if x.strip() and not x.lstrip().startswith('#') and not (skip_header and i == 0)}


class PassiveObserver:
    """Call on_step(traci) ONCE immediately after the caller's simulationStep().

    out_dir must be new. close() flushes and records provenance. Observing does not
    imply calibration against Quito, confirmed signal violations or actual gridlock.
    """
    def __init__(self, out_dir, *, condition="unspecified", seed=None, vine_ids=(), h09_ids=(),
                 approach_distance_m=80., stop_threshold_m_s=0.1,
                 stop_min_duration_s=2.0, strict=True):
        self.out_dir = Path(out_dir).resolve()
        if self.out_dir.exists():
            raise FileExistsError(f"Salidas H11.2 ya existen; no sobrescribir: {self.out_dir}")
        if not (approach_distance_m > 0 and stop_min_duration_s > 0):
            raise ValueError("Distancia de aproximación y duración deben ser positivas")
        self.out_dir.mkdir(parents=True, exist_ok=False)
        self.config = dict(version=VERSION, condition=condition, seed=seed,
            approach_distance_m=approach_distance_m, stop_threshold_m_s=stop_threshold_m_s,
            stop_min_duration_s=stop_min_duration_s, strict=bool(strict),
            population_definition="caller_supplied_rosters", empirically_calibrated_quito=False)
        self.strict = strict
        self.vine_ids = set(map(str, vine_ids))
        self.h09_ids = set(map(str, h09_ids))
        self.config["vine_roster_count"] = len(self.vine_ids)
        self.config["h09_roster_count"] = len(self.h09_ids)
        self.counts = Counter()
        self.errors = Counter()
        self.last = {}
        self.episode_by_key = Counter()
        self.last_approach_at = {}
        self.opportunities = set()
        self.crossings = set()
        self.internal_stops = {}
        self.last_time = None
        self.closed = False
        self.handles = {}
        self.writers = {}
        for filename, columns in [("trayectorias_h11.csv", TRAJ_COLS),
                                  ("eventos_semaforicos_h11.csv", TLS_COLS),
                                  ("eventos_interseccion_h11.csv", INT_COLS),
                                  ("seguridad_h11.csv", SAFE_COLS)]:
            handle = (self.out_dir / filename).open("x", newline="", encoding="utf-8")
            w = csv.DictWriter(handle, fieldnames=columns, extrasaction="raise")
            w.writeheader()
            self.handles[filename] = handle
            self.writers[filename] = w

    def _get(self, obj, name, *args):
        method = getattr(obj, name, None)
        if not callable(method):
            self.errors[f"not_supported:{name}"] += 1
            return None
        try:
            return method(*args)
        except Exception as exc:
            self.errors[f"failed:{name}:{type(exc).__name__}"] += 1
            return None

    def _required(self, obj, name, *args):
        method = getattr(obj, name, None)
        if not callable(method):
            raise RuntimeError(f"Consulta TraCI obligatoria no disponible: {name}")
        return method(*args)

    def _cohort(self, vid):
        v, h = vid in self.vine_ids, vid in self.h09_ids
        return "both" if v and h else "vine_only" if v else "h09_only" if h else "neither" if self.vine_ids or self.h09_ids else "unclassified"

    def _tls_state_at_time(self, traci, tls_id, link_idx):
        lights = self._get(traci.trafficlight, "getRedYellowGreenState", tls_id)
        if lights is None or link_idx is None:
            return None
        try:
            return str(lights[int(link_idx)])
        except (IndexError, TypeError, ValueError):
            self.errors["invalid_tls_index"] += 1
            return None

    def _internal_stop_end(self, vid, end_t, *, censored=False):
        start = self.internal_stops.pop(vid, None)
        if not start:
            return
        duration = max(0., end_t - start["start_s"])
        if duration < self.config["stop_min_duration_s"]:
            return
        row = {**start, "vehicle_id":vid,"end_s":end_t,"duration_s":duration,
               "event_kind":"stopped_on_internal_lane_candidate", "gridlock_confirmed":"false",
               "evidence_quality":"PROXY_ONLY_no_obstructed_flows_verified", "censored_end":str(bool(censored)).lower()}
        self.writers["eventos_interseccion_h11.csv"].writerow(row)
        self.counts["internal_stop_candidates"] += 1

    def _csv_tls(self, row):
        self.writers["eventos_semaforicos_h11.csv"].writerow(row)
        self.counts["tls_" + row["event_kind"]] += 1

    def _new_episode(self, vid, tls_id, index, t, dt):
        key=(vid, tls_id, index)
        previous=self.last_approach_at.get(key)
        if previous is None or (t - previous) > max(3 * dt, 1.5):
            self.episode_by_key[key] += 1
        self.last_approach_at[key]=t
        return f"{vid}|{tls_id}|{index}|{self.episode_by_key[key]}"

    def on_step(self, traci, step=None):
        if self.closed:
            raise RuntimeError("Observador cerrado")
        sim=traci.simulation
        t=_num(self._required(sim,"getTime"))
        dt=_num(self._required(sim,"getDeltaT"))
        if t is None or dt is None or dt <= 0:
            raise RuntimeError("Tiempo o paso SUMO inválido")
        if self.last_time is not None and t <= self.last_time + 1e-9:
            raise RuntimeError(f"Doble observación o tiempo no monótono: {t}")
        self.last_time=t
        idx=self.counts["steps"] if step is None else int(step)
        self.counts["steps"] += 1
        ids=sorted(map(str, self._required(traci.vehicle,"getIDList")))
        current = {}
        for vid in ids:
            lane=self._get(traci.vehicle,"getLaneID",vid)
            road=self._get(traci.vehicle,"getRoadID",vid)
            speed=_num(self._get(traci.vehicle,"getSpeed",vid))
            accel=_num(self._get(traci.vehicle,"getAcceleration",vid))
            position=_num(self._get(traci.vehicle,"getLanePosition",vid))
            xy=self._get(traci.vehicle,"getPosition",vid)
            xy=(xy[0],xy[1]) if isinstance(xy,(tuple,list)) and len(xy)>1 else (None,None)
            max_speed=_num(self._get(traci.lane,"getMaxSpeed",lane)) if lane else None
            allowed=_num(self._get(traci.vehicle,"getAllowedSpeed",vid))
            prev=self.last.get(vid)
            jerk=None
            if prev and prev.get("a") is not None and accel is not None:
                elapsed=t-prev["t"]
                if 0 < elapsed <= max(1.5*dt,dt+1e-6):
                    jerk=(accel-prev["a"])/elapsed
            leader=self._get(traci.vehicle,"getLeader",vid,1000.0)
            leader_id, gap=(None,None)
            if leader and len(leader)>=2 and str(leader[0]):
                leader_id=str(leader[0]);gap=_num(leader[1])
            lv=_num(self._get(traci.vehicle,"getSpeed",leader_id)) if leader_id else None
            closing=(speed-lv) if speed is not None and lv is not None else None
            headway=(gap/speed) if gap is not None and speed is not None and speed>1e-6 and gap>=0 else None
            ttc=(gap/closing) if gap is not None and closing is not None and closing>1e-6 and gap>=0 else None
            tls=self._get(traci.vehicle,"getNextTLS",vid)
            upcoming=None
            if tls:
                for item in tls:
                    if len(item)>=4 and _num(item[2]) is not None and _num(item[2])>=0:
                        upcoming=(str(item[0]),int(item[1]),_num(item[2]),str(item[3]))
                        break
            tls_id,link_idx,dist,state = upcoming if upcoming else (None,None,None,None)
            road=str(road) if road is not None else None
            lane=str(lane) if lane is not None else None
            internal=bool((lane and lane.startswith(':')) or (road and road.startswith(':')))
            next_lane=None; next_halted=None; next_n=None
            if internal:
                links=self._get(traci.vehicle,"getNextLinks",vid)
                if links and len(links[0])>0:
                    next_lane=str(links[0][0])
                    next_halted=self._get(traci.lane,"getLastStepHaltingNumber",next_lane)
                    next_n=self._get(traci.lane,"getLastStepVehicleNumber",next_lane)
            limit_exceeded=(speed>max_speed+1e-6) if speed is not None and max_speed is not None else None
            required_stop=(speed**2/(2*dist)) if speed is not None and dist is not None and dist>0 else None
            cohort=self._cohort(vid)
            traj=dict(step=idx,time_s=t,dt_s=dt,vehicle_id=vid,cohort=cohort,
                vtype=self._get(traci.vehicle,"getTypeID",vid),road_id=road,lane_id=lane,
                internal_lane=str(internal).lower(), lane_pos_m=position,x_m=_num(xy[0]),y_m=_num(xy[1]),
                speed_m_s=speed,speed_kmh=(speed*3.6 if speed is not None else None),
                accel_m_s2=accel,jerk_observed_m_s3=jerk,
                posted_lane_limit_m_s=max_speed,allowed_speed_m_s=allowed,
                above_posted_lane_limit=str(limit_exceeded).lower() if limit_exceeded is not None else "unknown",
                leader_id=leader_id,gap_m=gap,leader_speed_m_s=lv,closing_speed_m_s=closing,
                headway_s=headway,ttc_s=ttc,tls_id=tls_id,tls_link_index=link_idx,
                tls_state=state or "unknown",tls_distance_m=dist,required_stop_decel_m_s2=required_stop,
                next_lane_id=next_lane,next_lane_halted=next_halted,next_lane_n_vehicles=next_n)
            self.writers["trayectorias_h11.csv"].writerow(traj)
            self.counts["trajectory_rows"] += 1
            if limit_exceeded:
                self.counts["above_posted_limit_vehicle_steps"] += 1
            # One opportunity for each episode and colour observed within approach horizon.
            episode=None
            if tls_id is not None and dist is not None and dist <= self.config["approach_distance_m"]:
                episode=self._new_episode(vid,tls_id,link_idx,t,dt)
                label=_color(state)
                mark=(episode,label)
                if mark not in self.opportunities:
                    self.opportunities.add(mark)
                    self._csv_tls(dict(step=idx,time_s=t,vehicle_id=vid,cohort=cohort,
                        event_kind="approach_opportunity_proxy",tls_id=tls_id,link_index=link_idx,
                        episode_id=episode,lane_before=lane,lane_after="",road_before=road,road_after="",
                        state_previous=state,state_current=state,distance_previous_m=dist,
                        distance_current_m=dist,speed_previous_m_s=speed,
                        required_stop_decel_m_s2=required_stop,color_label=label,
                        quality="opportunity_proxy_not_human_decision",notes="first observation of signal colour in episode"))
            # Stop-line transition proxy: previous approach and entering an internal lane/edge.
            if prev and prev.get("tls") and prev.get("dist") is not None:
                p_tls,p_index,p_dist,p_state=prev["tls"],prev["idx"],prev["dist"],prev["signal"]
                crossing_edge=(not prev.get("internal") and internal) or (road is not None and prev.get("road") is not None and road != prev["road"])
                plausible=(p_dist <= max(10.,(prev.get("speed") or 0.)*dt*1.5+5.))
                still_same=(tls_id==p_tls and link_idx==p_index and dist is not None and p_dist is not None and dist>p_dist+3.)
                if crossing_edge and plausible and not still_same:
                    # Approximate previous episode key; its colour is from PREVIOUS step.
                    p_episode=prev.get("episode")
                    if p_episode and p_episode not in self.crossings:
                        self.crossings.add(p_episode)
                        phase_now=self._tls_state_at_time(traci,p_tls,p_index)
                        same=(_color(p_state)==_color(phase_now) and _color(p_state)!="unknown")
                        classification=_color(p_state) if same else "unknown"
                        self._csv_tls(dict(step=idx,time_s=t,vehicle_id=vid,cohort=cohort,
                            event_kind="crossing_proxy",tls_id=p_tls,link_index=p_index,
                            episode_id=p_episode,lane_before=prev.get("lane"),lane_after=lane,
                            road_before=prev.get("road"),road_after=road,
                            state_previous=p_state,state_current=phase_now if phase_now is not None else "unknown",
                            distance_previous_m=p_dist,distance_current_m=dist,
                            speed_previous_m_s=prev.get("speed"),
                            required_stop_decel_m_s2=(prev["speed"]**2/(2*p_dist) if p_dist>0 and prev.get("speed") is not None else None),
                            color_label=classification,
                            quality="PROXY_signal_stable" if same else "UNKNOWN_signal_transition_or_missing",
                            notes="road/lane transition near previous stop-line; NOT a confirmed legal violation"))
            # Candidate internal-lane stop: NEVER claim proven gridlock.
            if internal and speed is not None and speed < self.config["stop_threshold_m_s"]:
                if vid not in self.internal_stops:
                    self.internal_stops[vid]=dict(cohort=cohort,road_id=road,lane_id=lane,
                        start_s=t,min_speed_m_s=speed,next_lane_id=next_lane,
                        next_lane_halted=next_halted,next_lane_n_vehicles=next_n)
                else:
                    self.internal_stops[vid]["min_speed_m_s"] = min(speed,self.internal_stops[vid]["min_speed_m_s"])
            else:
                self._internal_stop_end(vid,t)
            current[vid]=dict(t=t,a=accel,lane=lane,road=road,internal=internal,
                speed=speed,tls=tls_id,idx=link_idx,dist=dist,signal=state,
                episode=episode)
        for departed_id in set(self.last)-set(current):
            self._internal_stop_end(departed_id,t,censored=True)
        self.last=current
        # Safety: retain unavailable values as blanks (never invent zero).
        count_specs=[("colliding_vehicles_count","getCollidingVehiclesNumber"),
                     ("teleport_start_count","getStartingTeleportNumber"),
                     ("emergency_stop_count","getEmergencyStoppingVehiclesNumber")]
        id_specs=[("colliding_vehicle_ids","getCollidingVehiclesIDList"),
                  ("teleport_start_ids","getStartingTeleportIDList"),
                  ("emergency_stop_ids","getEmergencyStoppingVehiclesIDList")]
        row=dict(step=idx,time_s=t)
        for key,method in count_specs:
            row[key]=self._get(sim,method)
        for key,method in id_specs:
            value=self._get(sim,method)
            row[key]="|".join(sorted(map(str,value))) if value is not None else ""
        row["telemetry_errors"]=sum(self.errors.values())
        self.writers["seguridad_h11.csv"].writerow(row)
        return {"step":idx,"time_s":t,"n_vehicles":len(ids)}

    def close(self):
        if self.closed: return
        for vid in list(self.internal_stops):
            self._internal_stop_end(vid,self.last_time or 0.,censored=True)
        for f in self.handles.values(): f.close()
        checksums={}
        for name in sorted(self.handles):
            checksums[name]=hashlib.sha256((self.out_dir/name).read_bytes()).hexdigest()
        manifest={**self.config,"created_utc":datetime.now(timezone.utc).isoformat(),
            "observed_steps":self.counts.get("steps",0),"last_observed_time_s":self.last_time,
            "counts":dict(self.counts),"telemetry_failures_or_missing":dict(self.errors),
            "outputs_sha256":checksums,
            "methodological_limits":["No Quito field calibration", "Crossings are proxies; not legally established violations",
              "Internal stopped candidate != confirmed gridlock", "The observer is read-only; control changes not attributable", 
              "Vine/H09 membership only known if authoritative IDs supplied"]}
        (self.out_dir / "manifest_h11_2.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
        self.closed=True

    def __enter__(self): return self
    def __exit__(self, *exc): self.close()
