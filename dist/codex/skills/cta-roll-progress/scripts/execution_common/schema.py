"""Validator for the explicit schema subset emitted by this project, not arbitrary schemas."""
import re
from .values import require


def validate(value, schema, path='$'):
    def check(ok): require(ok,'INVALID_REQUEST',path=path)
    kind=schema.get('type')
    types={'object':isinstance(value,dict),'array':isinstance(value,list),'string':isinstance(value,str),'integer':type(value) is int,'boolean':type(value) is bool,'null':value is None}
    if kind: check(any(types.get(k,False) for k in (kind if isinstance(kind,list) else [kind])))
    if 'const' in schema: check(value==schema['const'])
    if 'enum' in schema: check(value in schema['enum'])
    if 'minimum' in schema: check(value>=schema['minimum'])
    if 'minLength' in schema: check(len(value)>=schema['minLength'])
    if 'pattern' in schema: check(re.fullmatch(schema['pattern'],value) is not None)
    if isinstance(value,dict):
        check(set(schema.get('required',[]))<=set(value))
        properties=schema.get('properties',{})
        if schema.get('additionalProperties') is False: check(set(value)<=set(properties))
        for k,v in value.items():
            if k in properties: validate(v,properties[k],path+'.'+k)
    if isinstance(value,list) and 'items' in schema:
        for i,v in enumerate(value): validate(v,schema['items'],path+f'[{i}]')
