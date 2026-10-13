#!/usr/bin/env python3
"""Compare exact bytes of preexisting traffic summary vs a NEW equivalent run.
Both files must encode same condition, seed, inputs and horizon.
"""
import argparse
import hashlib
from pathlib import Path

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--original',type=Path,required=True)
    p.add_argument('--nuevo',type=Path,required=True)
    a=p.parse_args()
    if a.original.resolve()==a.nuevo.resolve(): raise ValueError('No comparar el mismo archivo contra sí mismo')
    old,new=sha(a.original),sha(a.nuevo)
    print('ORIGINAL SHA256',old)
    print('NUEVO    SHA256',new)
    if old != new:
        print('DIFERENCIA: archivos no idénticos. Verificar mismo escenario, semilla, horizonte, scripts y entradas.')
        raise SystemExit(2)
    print('IGUALES: los dos archivos de tráfico son idénticos byte a byte.')

if __name__=='__main__':main()
