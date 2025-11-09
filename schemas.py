"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
Each Pydantic model represents a collection in your database.
Class name is converted to lowercase for the collection name.
"""

from pydantic import BaseModel, Field, HttpUrl
from typing import Optional
from datetime import datetime

# Example schemas kept for reference
class User(BaseModel):
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    address: str = Field(..., description="Address")
    age: Optional[int] = Field(None, ge=0, le=120, description="Age in years")
    is_active: bool = Field(True, description="Whether user is active")

class Product(BaseModel):
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in dollars")
    category: str = Field(..., description="Product category")
    in_stock: bool = Field(True, description="Whether product is in stock")

# Application schemas

class Exam(BaseModel):
    """
    Collection: "exam"
    Stores each scheduled exam with an external URL and a password hash.
    """
    url: HttpUrl = Field(..., description="External form URL to embed")
    password_hash: str = Field(..., description="SHA-256 hash of password")
    slug: str = Field(..., description="Short slug for public access")
    created_at: datetime
    updated_at: datetime

class Examlog(BaseModel):
    """
    Collection: "examlog"
    Stores proctoring events for an exam.
    """
    exam_id: str
    type: str
    details: Optional[str] = ""
    client_ts: Optional[int] = None
    server_ts: datetime
    ip: Optional[str] = None
    ua: Optional[str] = None
