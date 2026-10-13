#!/usr/bin/env python3
"""Explicit, reversible post-step hook for an existing TraCI script (same Python process).

No sitecustomize magic: h11_2_ejecutar_h10.py calls install() before runpy.
"""
from pathlib import Path
from datetime import datetime
import os
from h11_2_observador_pasivo import PassiveObserver

class TraCIObserverHook:
    def __init__(self, traci, outdir, *, condition, seed=None, vine_ids=(), h09_ids=()):
        self.traci = traci
        self.outdir=Path(outdir)
        self.condition=condition
        self.seed=seed
        self.vine_ids=vine_ids
        self.h09_ids=h09_ids
        self.depth=0
        self.obs=None
        self.originals=[]
        self._patch(traci,'simulationStep')
        if hasattr(traci,'connection') and hasattr(traci.connection,'Connection'):
            self._patch(traci.connection.Connection,'simulationStep')

    def _patch(self,obj,name):
        original=getattr(obj,name,None)
        if not callable(original): return
        self.originals.append((obj,name,original))
        def post_step(*args,**kwargs):
            if self.depth:
                return original(*args,**kwargs)
            self.depth+=1
            try:
                result=original(*args,**kwargs)
                if self.obs is None:
                    self.obs=PassiveObserver(self.outdir,condition=self.condition,seed=self.seed,
                        vine_ids=self.vine_ids,h09_ids=self.h09_ids)
                # original advanced SUMO already; one QUERY-ONLY observation.
                self.obs.on_step(self.traci)
                return result
            finally:
                self.depth-=1
        setattr(obj,name,post_step)

    def close(self):
        for obj,name,original in reversed(self.originals):
            setattr(obj,name,original)
        self.originals.clear()
        if self.obs: self.obs.close()


def install(traci, outdir, **kwargs):
    return TraCIObserverHook(traci,outdir,**kwargs)
