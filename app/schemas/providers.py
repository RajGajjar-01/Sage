from pydantic import BaseModel


class SwitchProviderRequest(BaseModel):
    name: str
