# app/services/session_service.py
from datetime import datetime, timedelta
from app.models.vehicle_session import VehicleSession


class SessionService:
    @staticmethod
    async def mark_abandoned_sessions(timeout_minutes: int = 10) -> int:
        """
        OPEN -> ABANDONED if lastSeenAt older now - timeout
        return: number of sessions updated
        """
        cutoff = datetime.utcnow() - timedelta(minutes=timeout_minutes)

        # condition: OPEN and lastSeenAt < cutoff
        result = await VehicleSession.find(
            VehicleSession.status == "OPEN",
            VehicleSession.lastSeenAt != None,  # exclude null cases
            VehicleSession.lastSeenAt < cutoff,
        ).update(
            {"$set": {"status": "ABANDONED", "updatedAt": datetime.utcnow()}}
        )

        # Beanie update() returns UpdateResult (raw) in some versions
        # To be sure: use modified_count if available
        return getattr(result, "modified_count", 0)

    @staticmethod
    async def mark_stale_open_sessions_without_lastseen(timeout_minutes: int = 10) -> int:
        """
        Handle cases where lastSeenAt is None (e.g., entry created but never updated)
        Use createdAt instead
        """
        cutoff = datetime.utcnow() - timedelta(minutes=timeout_minutes)

        result = await VehicleSession.find(
            VehicleSession.status == "OPEN",
            VehicleSession.lastSeenAt == None,
            VehicleSession.createdAt < cutoff,
        ).update(
            {"$set": {"status": "ABANDONED", "updatedAt": datetime.utcnow()}}
        )

        return getattr(result, "modified_count", 0)
