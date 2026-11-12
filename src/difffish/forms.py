"""
Pydantic models for each WCS field note form type.

Canonical geo fields (consistent across ALL form types):
  state    — state abbreviation or name as written
  county   — county name (no "County" suffix)
  lat      — latitude as written (e.g. "35.5873 N")
  lon      — longitude as written (e.g. "84.046 W")
  locality — full locality description
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, create_model


# ---------------------------------------------------------------------------
# Shared sub-models
# ---------------------------------------------------------------------------

class SpeciesEntry(BaseModel):
    number: str = ""
    name: str = ""
    count: str = ""
    notes: str = ""


# ---------------------------------------------------------------------------
# Per-form models
# ---------------------------------------------------------------------------

class FreshwaterSection(BaseModel):
    continent: str = ""
    principal_drainage: str = ""
    river_subbasins: str = ""
    country: str = ""
    state: str = ""          # CANONICAL


class MarineSection(BaseModel):
    ocean: str = ""
    ocean_subbasin: str = ""
    country: str = ""
    state: str = ""          # CANONICAL


class LocaleSection(BaseModel):
    county: str = ""         # CANONICAL
    map_sheet: str = ""
    locality: str = ""       # CANONICAL
    lat: str = ""            # CANONICAL
    lon: str = ""            # CANONICAL
    other_coords: str = ""
    collectors: str = ""
    method_capture: str = ""
    depth_capture: str = ""
    preservative: str = ""


class EcologySection(BaseModel):
    general_habitat: str = ""
    stream_width: str = ""
    max_depth: str = ""
    current: str = ""
    color: str = ""
    temp: str = ""
    salinity: str = ""
    bottom_type: str = ""
    vegetation: str = ""
    shore_type: str = ""


class NcsmSheet(BaseModel):
    """North Carolina State Museum Aquatic/Marine Field Data Sheet."""
    form_type: Literal["ncsm_sheet"] = "ncsm_sheet"
    date: str = ""
    time: str = ""
    field_num: str = ""
    freshwater: FreshwaterSection = Field(default_factory=FreshwaterSection)
    marine: MarineSection = Field(default_factory=MarineSection)
    locale: LocaleSection = Field(default_factory=LocaleSection)
    ecology: EcologySection = Field(default_factory=EcologySection)
    acc_num: str = ""
    notes: str = ""


class StarnesCard(BaseModel):
    """W.C. Starnes Collections card."""
    form_type: Literal["starnes_card"] = "starnes_card"
    coll_num: str = ""
    continent: str = ""
    country: str = ""
    drainage: str = ""
    state: str = ""          # CANONICAL
    county: str = ""         # CANONICAL
    locality: str = ""       # CANONICAL
    lat: str = ""            # CANONICAL (often blank on this form)
    lon: str = ""            # CANONICAL (often blank on this form)
    date: str = ""
    time: str = ""
    collectors: str = ""
    method: str = ""
    water_temp: str = ""
    current: str = ""
    width: str = ""
    depth: str = ""
    color: str = ""
    substrate: str = ""
    vegetation: str = ""
    environs: str = ""
    comments: str = ""


class SpeciesList(BaseModel):
    """Species list card (typed or handwritten)."""
    form_type: Literal["species_list"] = "species_list"
    drainage: str = ""
    coll_num: str = ""
    locality: str = ""       # CANONICAL (often contains state/county)
    date: str = ""
    collectors: str = ""
    species: list[SpeciesEntry] = Field(default_factory=list)


class SI806a(BaseModel):
    """Smithsonian Oceanographic Sorting Center Field Data Record (SI-806a)."""
    form_type: Literal["si_806a"] = "si_806a"
    date: str = ""
    field_num: str = ""
    sta_num: str = ""
    collectors: str = ""
    locality: str = ""       # CANONICAL (typically "ST, County, description")
    state: str = ""          # CANONICAL — parse from locality if needed
    county: str = ""         # CANONICAL — parse from locality if needed
    lat: str = ""            # CANONICAL
    lon: str = ""            # CANONICAL
    habitat: str = ""
    vegetation: str = ""
    bottom: str = ""
    water_temp: str = ""
    depth: str = ""
    method: str = ""
    preservative: str = ""
    species: list[SpeciesEntry] = Field(default_factory=list)


class CollectionCard(BaseModel):
    """Generic structured collection data card."""
    form_type: Literal["collection_card"] = "collection_card"
    system: str = ""
    date: str = ""
    coll_num: str = ""
    locality: str = ""       # CANONICAL
    state: str = ""          # CANONICAL
    county: str = ""         # CANONICAL
    lat: str = ""            # CANONICAL
    lon: str = ""            # CANONICAL
    depth: str = ""
    width: str = ""
    current: str = ""
    temp: str = ""
    substrate: str = ""
    collectors: str = ""
    notes: str = ""


class Freeform(BaseModel):
    """Free-form notes, sketch maps, or back-of-card text."""
    form_type: Literal["freeform"] = "freeform"
    text: str = ""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

FORM_TYPE_MAP: dict[str, type[BaseModel]] = {
    "ncsm_sheet":     NcsmSheet,
    "starnes_card":   StarnesCard,
    "species_list":   SpeciesList,
    "si_806a":        SI806a,
    "collection_card": CollectionCard,
    "freeform":       Freeform,
    "unknown":        Freeform,
}


# ---------------------------------------------------------------------------
# Dynamic per-document model builder
# ---------------------------------------------------------------------------

def build_document_model(page_types: dict[str, str]) -> type[BaseModel]:
    """
    Build a Pydantic model for a specific document based on its page classifications.

    page_types: {"page_1": "ncsm_sheet", "page_2": "starnes_card", ...}
    Returns a dynamically created BaseModel subclass.
    """
    fields: dict[str, Any] = {
        "transcription_notes": (str, ""),
    }
    for page_key in sorted(page_types):
        form_type = page_types[page_key]
        model_class = FORM_TYPE_MAP[form_type]
        fields[page_key] = (model_class, Field(default_factory=model_class))
    return create_model("FieldNoteDocument", **fields)
