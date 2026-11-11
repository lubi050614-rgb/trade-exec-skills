"""Validate the deliberately small JSON Schema vocabulary used by shipped contracts.

The exported schemas are also checked with the independent jsonschema validator in tests.
This is not a general JSON Schema implementation.
"""
import re
from .engine_errors import ContractError


def validate(value, schema, path='$'):
    def check(condition, reason):
        if not condition: raise ContractError(path+': '+reason)
    kind=schema.get('type')
    if kind:
        check({'object':isinstance(value,dict),'array':isinstance(value,list),'string':isinstance(value,str),
               'integer':type(value) is int,'boolean':type(value) is bool}.get(kind,False), 'expected '+kind)
    if 'const' in schema: check(value==schema['const'],'wrong constant')
    if 'enum' in schema: check(value in schema['enum'],'invalid enum')
    if 'minimum' in schema: check(value>=schema['minimum'],'below minimum')
    if 'pattern' in schema: check(re.fullmatch(schema['pattern'],value) is not None,'invalid decimal')
    if isinstance(value,dict):
        check(set(schema.get('required',[]))<=set(value),'missing required fields')
        properties=schema.get('properties',{})
        if schema.get('additionalProperties') is False: check(set(value)<=set(properties),'unknown fields')
        for k,v in value.items():
            if k in properties: validate(v,properties[k],path+'.'+k)
    if isinstance(value,list) and 'items' in schema:
        for i,v in enumerate(value): validate(v,schema['items'],path+f'[{i}]')
    for clause in schema.get('allOf',[]):
        try: validate(value,clause['if'],path)
        except ContractError: branch=clause.get('else',{})
        else: branch=clause.get('then',{})
        validate(value,branch,path)
