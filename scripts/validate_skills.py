"""Apply an explicitly supplied official skill-creator validator to Codex projections."""
import argparse
import importlib.util
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(); p.add_argument('--validator',required=True); a=p.parse_args()
    spec=importlib.util.spec_from_file_location('skill_validator',a.validator)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    results=[]
    catalog=json.loads((ROOT/'contracts/catalog.json').read_text(encoding='utf-8'))
    for name in catalog:
        passed,message=module.validate_skill(ROOT/'dist/codex/skills'/name)
        results.append(dict(skill=name,passed=passed,message=message))
    for change in ('stock-execution-tools','cta-execution-tools'):
        (ROOT/'openspec/changes'/change/'skill-validation.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8')
    print(f"Codex skill validation: {sum(x['passed'] for x in results)} / {len(results)}")
    return 0 if results and all(x['passed'] for x in results) else 1


if __name__=='__main__': raise SystemExit(main())
