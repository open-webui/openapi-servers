from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware

# --- Nano Empire Monetization Patch ---
try:
    from nano_empire_guardrails import monetize
    original_add_api_route = FastAPI.add_api_route
    def monetized_add_api_route(self, path: str, endpoint, *args, **kwargs):
        if not any(path.startswith(prefix) for prefix in ["/docs", "/redoc", "/openapi"]):
            endpoint = monetize(credits_per_call=1)(endpoint)
        return original_add_api_route(self, path, endpoint, *args, **kwargs)
    FastAPI.add_api_route = monetized_add_api_route
except ImportError:
    pass
# --------------------------------------

from pydantic import BaseModel, Field
from typing import List, Literal, Union
from pathlib import Path
import json
import os

app = FastAPI(
    title="Knowledge Graph Server",
    version="1.0.0",
    description="A structured knowledge graph memory system that supports entity and relation storage, observation tracking, and manipulation.",
)

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----- Persistence Setup -----
MEMORY_FILE_PATH_ENV = os.getenv("MEMORY_FILE_PATH", "memory.json")
MEMORY_FILE_PATH = Path(
    MEMORY_FILE_PATH_ENV
    if Path(MEMORY_FILE_PATH_ENV).is_absolute()
    else Path(__file__).parent / MEMORY_FILE_PATH_ENV
)


# ----- Data Models -----
class Entity(BaseModel):
    name: str = Field(..., description="The name of the entity")
    entityType: str = Field(..., description="The type of the entity")
    observations: List[str] = Field(
        ..., description="An array of observation contents associated with the entity"
    )


class Relation(BaseModel):
    from_: str = Field(
        ...,
        alias="from",
        description="The name of the entity where the relation starts",
    )
    to: str = Field(..., description="The name of the entity where the relation ends")
    relationType: str = Field(..., description="The type of the relation")


class KnowledgeGraph(BaseModel):
    entities: List[Entity]
    relations: List[Relation]


class EntityWrapper(BaseModel):
    type: Literal["entity"]
    name: str
    entityType: str
    observations: List[str]


class RelationWrapper(BaseModel):
    type: Literal["relation"]
    from_: str = Field(..., alias="from")
    to: str
    relationType: str


# ----- I/O Handlers -----
def read_graph_file() -> KnowledgeGraph:
    if not MEMORY_FILE_PATH.exists():
        return KnowledgeGraph(entities=[], relations=[])
    with open(MEMORY_FILE_PATH, "r", encoding="utf-8") as f:
        lines = [line for line in f if line.strip()]
        entities = []
        relations = []
        for line in lines:
            print(line)
            item = json.loads(line)
            if item["type"] == "entity":
                entities.append(
                    Entity(
                        name=item["name"],
                        entityType=item["entityType"],
                        observations=item["observations"],
                    )
                )
            elif item["type"] == "relation":
                relations.append(Relation(**item))

        return KnowledgeGraph(entities=entities, relations=relations)


def save_graph(graph: KnowledgeGraph):
    lines = [json.dumps({"type": "entity", **e.dict()}) for e in graph.entities] + [
        json.dumps({"type": "relation", **r.dict(by_alias=True)})
        for r in graph.relations
    ]
    with open(MEMORY_FILE_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ----- Request Models -----


class CreateEntitiesRequest(BaseModel):
    entities: List[Entity] = Field(..., description="List of entities to create")


class CreateRelationsRequest(BaseModel):
    relations: List[Relation] = Field(
        ..., description="List of relations to create. All must be in active voice."
    )


class ObservationItem(BaseModel):
    entityName: str = Field(
        ..., description="The name of the entity to add the observations to"
    )
    contents: List[str] = Field(
        ..., description="An array of observation contents to add"
    )


class DeletionItem(BaseModel):
    entityName: str = Field(
        ..., description="The name of the entity containing the observations"
    )
    observations: List[str] = Field(
        ..., description="An array of observations to delete"
    )


class AddObservationsRequest(BaseModel):
    observations: List[ObservationItem] = Field(
        ...,
        description="A list of observation additions, each specifying an entity and contents to add",
    )


class DeleteObservationsRequest(BaseModel):
    deletions: List[DeletionItem] = Field(
        ...,
        description="A list of observation deletions, each specifying an entity and observations to remove",
    )


class DeleteEntitiesRequest(BaseModel):
    entityNames: List[str] = Field(
        ..., description="An array of entity names to delete"
    )


class DeleteRelationsRequest(BaseModel):
    relations: List[Relation] = Field(
        ..., description="An array of relations to delete"
    )


class SearchNodesRequest(BaseModel):
    query: str = Field(
        ...,
        description="The search query to match against entity names, types, and observation content",
    )


class OpenNodesRequest(BaseModel):
    names: List[str] = Field(..., description="An array of entity names to retrieve")


# ----- Endpoints -----


@app.post("/create_entities", summary="Create multiple entities in the graph")
def create_entities(req: CreateEntitiesRequest):
    graph = read_graph_file()
    existing_names = {e.name for e in graph.entities}
    new_entities = [e for e in req.entities if e.name not in existing_names]
    graph.entities.extend(new_entities)
    save_graph(graph)
    return new_entities


@app.post("/create_relations", summary="Create multiple relations between entities")
def create_relations(req: CreateRelationsRequest):
    graph = read_graph_file()
    existing = {(r.from_, r.to, r.relationType) for r in graph.relations}
    new = [r for r in req.relations if (r.from_, r.to, r.relationType) not in existing]
    graph.relations.extend(new)
    save_graph(graph)
    return new


@app.post("/add_observations", summary="Add new observations to existing entities")
def add_observations(req: AddObservationsRequest):
    graph = read_graph_file()
    results = []

    for obs in req.observations:
        name = obs.entityName.lower()
        contents = obs.contents
        entity = next((e for e in graph.entities if e.name == name), None)
        if not entity:
            raise HTTPException(status_code=404, detail=f"Entity {name} not found")
        added = [c for c in contents if c not in entity.observations]
        entity.observations.extend(added)
        results.append({"entityName": name, "addedObservations": added})

    save_graph(graph)
    return results


@app.post("/delete_entities", summary="Delete entities and associated relations")
def delete_entities(req: DeleteEntitiesRequest):
    graph = read_graph_file()
    graph.entities = [e for e in graph.entities if e.name not in req.entityNames]
    graph.relations = [
        r
        for r in graph.relations
        if r.from_ not in req.entityNames and r.to not in req.entityNames
    ]
    save_graph(graph)
    return {"message": "Entities deleted successfully"}


@app.post("/delete_observations", summary="Delete specific observations from entities")
def delete_observations(req: DeleteObservationsRequest):
    graph = read_graph_file()

    for deletion in req.deletions:
        name = deletion.entityName.lower()
        to_delete = deletion.observations
        entity = next((e for e in graph.entities if e.name == name), None)
        if entity:
            entity.observations = [
                obs for obs in entity.observations if obs not in to_delete
            ]

    save_graph(graph)
    return {"message": "Observations deleted successfully"}


@app.post("/delete_relations", summary="Delete relations from the graph")
def delete_relations(req: DeleteRelationsRequest):
    graph = read_graph_file()
    del_set = {(r.from_, r.to, r.relationType) for r in req.relations}
    graph.relations = [
        r for r in graph.relations if (r.from_, r.to, r.relationType) not in del_set
    ]
    save_graph(graph)
    return {"message": "Relations deleted successfully"}


@app.get(
    "/read_graph", response_model=KnowledgeGraph, summary="Read entire knowledge graph"
)
def read_graph():
    return read_graph_file()


@app.post(
    "/search_nodes",
    response_model=KnowledgeGraph,
    summary="Search for nodes by keyword",
)
def search_nodes(req: SearchNodesRequest):
    graph = read_graph_file()
    print(graph)
    entities = [
        e
        for e in graph.entities
        if req.query.lower() in e.name.lower()
        or req.query.lower() in e.entityType.lower()
        or any(req.query.lower() in o.lower() for o in e.observations)
    ]
    names = {e.name for e in entities}
    relations = [r for r in graph.relations if r.from_ in names and r.to in names]

    print(names, relations)
    return KnowledgeGraph(entities=entities, relations=relations)


@app.post(
    "/open_nodes", response_model=KnowledgeGraph, summary="Open specific nodes by name"
)
def open_nodes(req: OpenNodesRequest):
    graph = read_graph_file()
    entities = [e for e in graph.entities if e.name in req.names]
    names = {e.name for e in entities}
    relations = [r for r in graph.relations if r.from_ in names and r.to in names]
    return KnowledgeGraph(entities=entities, relations=relations)
