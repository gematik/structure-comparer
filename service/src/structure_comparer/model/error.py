from pydantic import BaseModel


class Error(BaseModel):
    error: str

    @staticmethod
    def from_except(e: Exception) -> "Error":
        return Error(error=str(e))
