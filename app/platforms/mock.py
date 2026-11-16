"""Offline simulation, deliberately unable to return publication evidence."""
from app.schemas import PlatformName, PlatformResult


class MockAdapter:
    def __init__(self, name: PlatformName):
        self.name = name

    async def simulate(self) -> PlatformResult:
        return PlatformResult(platform=self.name, mode="mock", status="simulated",
                              warnings=["MOCK MODE: no API request was made and no post was published."])
