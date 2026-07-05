from pydantic import BaseModel


class SwitchProviderRequest(BaseModel):
    name: str


class ConnectProviderRequest(BaseModel):
    name: str
    api_key: str
    model: str
    endpoint: str
