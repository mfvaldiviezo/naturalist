#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera estaciones de velocidad en carriles de aproximacion TLS leyendo una red SUMO.

Solo lee .net.xml y escribe NUEVO JSON; no inicia ni modifica SUMO.
Las estaciones son de conveniencia instrumental, NO son equivalentes al muestreo BIGRS Quito.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET

def generate_zones(net,sites,upstream_far=45.,upstream_near=15.):
    if upstream_far<=upstream_near or upstream_near<=0:
        raise ValueError('Se exige 0 < upstream_near < upstream_far')
    root=ET.parse(str(net)).getroot()
    lanes={}
    for edge in root.findall('edge'):
        if edge.attrib.get('function')=='internal':continue
        for lane in edge.findall('lane'):
            try:
                lanes[lane.get('id')]=(float(lane.get('length')),float(lane.get('speed')))
            except (TypeError,ValueError):pass
    targets=set(sites)
    found=set();pairs=set()
    for conn in root.findall('connection'):
        tls=conn.get('tl')
        if tls not in targets:continue
        found.add(tls)
        lane=f"{conn.get('from')}_{conn.get('fromLane','0')}"
        pairs.add((tls,lane))
    absent=targets-found
    if absent:raise ValueError(f'Sitios sin conexiones TLS: {sorted(absent)}')
    zones=[];skipped=[]
    for tls,lane in sorted(pairs):
        meta=lanes.get(lane)
        if meta is None:skipped.append({'site':tls,'lane':lane,'reason':'lane_not_found'});continue
        length,speed=meta
        if length<=upstream_near+1 or speed<=0:
            skipped.append({'site':tls,'lane':lane,'reason':'lane_short_or_bad_speed'});continue
        near=max(0.,length-upstream_near)
        far=max(0.,length-upstream_far)
        if near-far<2:
            skipped.append({'site':tls,'lane':lane,'reason':'measurement_zone_too_short'});continue
        zones.append({'measurement_id':f'{tls}|{lane}|u{upstream_far:g}-{upstream_near:g}',
                      'lane_id':lane,'from_m':round(far,3),'to_m':round(near,3)})
    if not zones:raise ValueError('No hay zonas validas en la red')
    return zones,skipped

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--net',required=True,type=Path)
    p.add_argument('--sites',default='B1,B2,C1')
    p.add_argument('--salida',required=True,type=Path)
    p.add_argument('--upstream-far',type=float,default=45.)
    p.add_argument('--upstream-near',type=float,default=15.)
    args=p.parse_args()
    sites=[x.strip() for x in args.sites.split(',') if x.strip()]
    if not args.net.is_file():p.error('Red no encontrada')
    if args.salida.exists():raise FileExistsError('No se sobreescribe '+str(args.salida))
    zones,skipped=generate_zones(args.net,sites,args.upstream_far,args.upstream_near)
    args.salida.parent.mkdir(parents=True,exist_ok=True)
    args.salida.write_text(json.dumps(zones,indent=2,ensure_ascii=False),encoding='utf-8')
    print('ESTACIONES GENERADAS:',len(zones),'DESCARTADAS:',len(skipped))
    print('NOTA: no equivalentes al protocolo de muestreo de velocidad de Quito BIGRS.')
    for s in skipped:print('AVISO',s)
    print('JSON:',args.salida)
if __name__=='__main__':main()
