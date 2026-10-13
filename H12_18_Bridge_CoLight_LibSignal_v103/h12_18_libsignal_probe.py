"""Comprobador aislado de import + forward real (sin SUMO)."""
import argparse
import json
from pathlib import Path
import sys
import traceback

def run(root, source_sha, source_config_sha):
    root=Path(root).resolve(strict=True)
    sys.path.insert(0,str(root))
    # No cargar agent/__init__.py: arrastraría CityFlow incluso en SUMO.
    from h12_18_colight_loader import load_original_colight_net
    import torch
    from torch_geometric import __version__ as pyg_version
    import hashlib
    # Debe comparar contra hashes del preflight; nunca autodeterminar el valor esperado.
    if hashlib.sha256((root/'configs/tsc/colight.yml').read_bytes()).hexdigest()!=source_config_sha:
        raise RuntimeError('YAML CoLight cambió desde el preflight')
    ColightNet, origin=load_original_colight_net(root,source_sha)
    import yaml
    y=yaml.safe_load((root/'configs/tsc/colight.yml').read_text(encoding='utf8'))
    keys=['NODE_EMB_DIM','N_LAYERS','INPUT_DIM','OUTPUT_DIM','NUM_HEADS',
          'NODE_LAYER_DIMS_EACH_HEAD','OUTPUT_LAYERS']
    kwargs={k:y['model'][k] for k in keys};kwargs['batch_size']=1
    torch.manual_seed(101)
    model=ColightNet(4,2,[2]*12,**kwargs)
    model.eval()
    x=torch.arange(48,dtype=torch.float32).view(12,4)/100.
    e=torch.tensor([[i for i in range(11)]+[i+1 for i in range(11)],
                    [i+1 for i in range(11)]+[i for i in range(11)]],dtype=torch.long)
    with torch.no_grad():
        q=model(x=x,edge_index=e,train=False)
    assert q.shape==(12,2),'La red LibSignal no devolvió 12x2'
    assert torch.isfinite(q).all().item(),'Q de LibSignal contiene NaN/Inf'
    return dict(result='H12_18_REAL_COLIGHT_FORWARD_RANDOM_WEIGHTS_OK',
                colight_module=origin['upstream_source'],
                provenance=origin,
                torch_version=str(torch.__version__),
                torch_geometric_version=str(pyg_version),
                output_shape=list(q.shape),train='NO',checkpoint='NONE')

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--libsignal-dir',required=True)
    p.add_argument('--mode',choices=['deps'],required=True)
    p.add_argument('--expected-source-sha256',required=True)
    p.add_argument('--expected-config-sha256',required=True)
    a=p.parse_args()
    try:
        print(json.dumps(run(a.libsignal_dir,a.expected_source_sha256,a.expected_config_sha256),ensure_ascii=False))
    except Exception as e:
        print('H12_18_DEPENDENCY_OR_FORWARD_BLOCKED',type(e).__name__,str(e),file=sys.stderr)
        sys.exit(3)
