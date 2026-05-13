from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date
from enum import Enum




    

class AdminanduserCommunicationResponse(BaseModel):
    name:str | None = None
    phone: str
    email: str | None = None
