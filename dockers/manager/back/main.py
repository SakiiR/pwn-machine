import redis
redis_client = redis.StrictRedis('redis')


import ariadne

type_defs = ariadne.load_schema_from_path('schema')

query = ariadne.QueryType()
mutation = ariadne.MutationType()

@query.field('me')
def resolve_me(*_):
    return {
        'is_first_login': False,
    }

import auth

schema = ariadne.make_executable_schema(type_defs,
    query, mutation, ariadne.snake_case_fallback_resolvers)


from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles
from ariadne.asgi import GraphQL

app = Starlette(routes=[
    Mount('/', StaticFiles(directory='static', html=True)),
    Mount('/api', GraphQL(schema)),
])
