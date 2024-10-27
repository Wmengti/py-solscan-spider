from datetime import datetime

from pydantic import BaseModel


class SolscanResult(BaseModel):
    signature: str = "-",
    time: str = "-",
    action: str = "-",
    from_account: str = "-",
    to_account: str = "-",
    change_amount: str = "-",
    token: str = "-",
