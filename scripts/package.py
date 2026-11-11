"""Build deterministic self-contained plugin and per-skill ZIP archives."""
from pathlib import Path
import zipfile
import sys
import re
import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from stock_execution.engine import TOOLS as STOCK_TOOLS
from cta_execution.engine import TOOLS as CTA_TOOLS
TOOLS=STOCK_TOOLS+CTA_TOOLS


def archive(output, files, base, overrides=None):
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for f in sorted(files):
            if f.is_file() and '__pycache__' not in f.parts:
                info=zipfile.ZipInfo(f.relative_to(base).as_posix(),date_time=(2026,11,11,0,0,0))
                info.compress_type=zipfile.ZIP_DEFLATED
                z.writestr(info,(overrides or {}).get(info.filename,f.read_bytes()))


def main():
    out=ROOT/'dist'; out.mkdir(exist_ok=True)
    files=[ROOT/name for name in ('plugin.json','README.md','pyproject.toml','requirements-dev.txt','execution_tools_ai_spec.md')]
    for name in ('skills','examples','contracts','stock_execution','cta_execution','execution_common','scripts','tests','openspec'):
        files.extend((ROOT/name).rglob('*'))
    archive(out/'stock-execution-tools.zip',files,ROOT)
    archive(out/'execution-tools.zip',files,ROOT)
    cta_files=[f for f in files if not ('skills' in f.parts and f.relative_to(ROOT).parts[1] not in CTA_TOOLS)]
    manifest=json.loads((ROOT/'plugin.json').read_text(encoding='utf-8'))
    cta_manifest=dict(manifest,name='cta-execution-tools',description='24 independent futures simulation skills',skills=[x for x in manifest['skills'] if x['name'] in CTA_TOOLS])
    archive(out/'cta-execution-tools.zip',cta_files,ROOT,{'plugin.json':json.dumps(cta_manifest,ensure_ascii=False,indent=2).encode('utf-8')})
    for tool in TOOLS:
        folder=ROOT/'skills'/tool
        archive(out/(tool+'.zip'),list(folder.rglob('*')),folder.parent)
    # Native metadata stays intact; Codex gets its own supported frontmatter projection.
    codex=out/'codex'/'skills'
    import shutil
    for tool in TOOLS:
        target=codex/tool
        shutil.copytree(ROOT/'skills'/tool,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
        source=(target/'SKILL.md').read_text(encoding='utf-8')
        body=re.split(r'^---\s*$',source,flags=re.M)[2]
        domain='futures' if tool in CTA_TOOLS else 'stock'
        metadata=f'''---
name: {tool}
description: Execute the {tool} {domain} simulation interface using explicit JSON inputs and a persistent mock session.
allowed-tools:
  - skill_run_script
metadata:
  version: "{'0.2.0' if tool in CTA_TOOLS else '0.1.0'}"
  entry: scripts/run.py
  when_to_use: Explicit {tool} {domain} simulation requests.
---
'''
        (target/'SKILL.md').write_text(metadata+body,encoding='utf-8')
    archive(out/'stock-execution-codex.zip',list(codex.rglob('*')),codex.parent)
    archive(out/'execution-tools-codex.zip',list(codex.rglob('*')),codex.parent)
    cta_codex=[f for tool in CTA_TOOLS for f in (codex/tool).rglob('*')]
    archive(out/'cta-execution-codex.zip',cta_codex,codex.parent)
    print('Built combined plugin, CTA plugin, 45 standalone skills and Codex projections in dist/')


if __name__=='__main__': main()
