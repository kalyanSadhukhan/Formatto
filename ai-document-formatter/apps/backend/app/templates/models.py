from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.domain.schemas.data_contracts import TemplateConstraint


class StylePropertyModel(BaseModel):
    font_name: Optional[str] = None
    font_size_pt: Optional[float] = None
    bold: Optional[bool] = None
    italic: Optional[bool] = None
    underline: Optional[bool] = None
    color: Optional[str] = None
    alignment: Optional[str] = None
    line_spacing: Optional[float] = None
    line_spacing_rule: Optional[str] = None
    space_before_pt: Optional[float] = None
    space_after_pt: Optional[float] = None
    left_indent_pt: Optional[float] = None
    right_indent_pt: Optional[float] = None
    first_line_indent_pt: Optional[float] = None
    hanging_indent_pt: Optional[float] = None
    outline_level: Optional[int] = None


class StyleDefinition(BaseModel):
    style_id: str
    style_name: str
    style_type: str  # paragraph, character, table, numbering
    based_on: Optional[str] = None
    next_style: Optional[str] = None
    is_custom: bool = False
    raw_declared_properties: StylePropertyModel = Field(default_factory=StylePropertyModel)
    inherited_properties: StylePropertyModel = Field(default_factory=StylePropertyModel)
    property_lineage: Dict[str, List[str]] = Field(default_factory=dict)
    resolved_effective_properties: StylePropertyModel = Field(default_factory=StylePropertyModel)
    undetermined_properties: List[str] = Field(default_factory=list)
    # Backward compatibility aliases
    direct_properties: StylePropertyModel = Field(default_factory=StylePropertyModel)
    resolved_properties: StylePropertyModel = Field(default_factory=StylePropertyModel)
    inheritance_chain: List[str] = Field(default_factory=list)


class SectionSettings(BaseModel):
    section_index: int
    break_type: str = "nextPage"  # nextPage, continuous, evenPage, oddPage
    page_width_pt: float
    page_height_pt: float
    orientation: str = "portrait"  # portrait, landscape
    page_size_name: Optional[str] = None  # A4, Letter, Custom
    margins_pt: Dict[str, float]  # top, bottom, left, right, header, footer, gutter
    columns_count: int = 1
    has_header: bool = False
    has_footer: bool = False
    is_header_linked: bool = False
    is_footer_linked: bool = False
    has_page_number: bool = False
    header_text: Optional[str] = None
    footer_text: Optional[str] = None
    header_rids: List[str] = Field(default_factory=list)
    footer_rids: List[str] = Field(default_factory=list)


class NumberingLevelDefinition(BaseModel):
    level: int
    num_fmt: str  # bullet, decimal, lowerLetter, etc.
    lvl_text: str  # "%1.", "•", etc.
    start: int = 1
    left_indent_pt: Optional[float] = None
    hanging_indent_pt: Optional[float] = None
    font_name: Optional[str] = None
    bold: Optional[bool] = None


class NumberingScheme(BaseModel):
    num_id: str
    abstract_num_id: Optional[str] = None
    levels: Dict[int, NumberingLevelDefinition] = Field(default_factory=dict)


class TableStyleDefinition(BaseModel):
    style_id: str
    style_name: Optional[str] = None
    has_borders: bool = False
    border_details: Dict[str, Any] = Field(default_factory=dict)
    cell_margins_pt: Dict[str, float] = Field(default_factory=dict)
    shading_color: Optional[str] = None


class TemplateTableStructure(BaseModel):
    """Metadata describing a pre-existing table inside a structured template document."""
    table_index: int
    rows_count: int
    columns_count: int
    header_texts: List[str] = Field(default_factory=list)
    has_merged_cells: bool = False
    is_form_table: bool = False
    signature_labels: List[str] = Field(default_factory=list)


class TemplateProfile(BaseModel):
    template_id: str
    file_path: Optional[str] = None
    document_defaults: Dict[str, Any] = Field(default_factory=dict)
    sections: List[SectionSettings] = Field(default_factory=list)
    styles: Dict[str, StyleDefinition] = Field(default_factory=dict)
    numbering_schemes: Dict[str, NumberingScheme] = Field(default_factory=dict)
    table_styles: Dict[str, TableStyleDefinition] = Field(default_factory=dict)
    template_tables: List[TemplateTableStructure] = Field(default_factory=list)
    is_structured_template: bool = False
    constraints: List[TemplateConstraint] = Field(default_factory=list)
    unsupported_features: List[Dict[str, Any]] = Field(default_factory=list)
    direct_formatting_overrides: List[Dict[str, Any]] = Field(default_factory=list)

