"""User referral & credit endpoints."""
from fastapi import APIRouter, Depends
from core import db, get_current_user, REFERRAL_BONUS

router = APIRouter(prefix="/api")


@router.get("/user/referral")
async def get_referral_info(user: dict = Depends(get_current_user)):
    referred_count = await db.users.count_documents({"referred_by": user["id"]})
    paid_count = await db.assignments.count_documents(
        {"user_id": {"$in": [u["id"] async for u in db.users.find({"referred_by": user["id"]}, {"id": 1})]},
         "status": {"$in": ["paid", "completed"]}}
    ) if referred_count else 0
    return {
        "referral_code": user["id"],
        "credits": round(float(user.get("credits") or 0), 2),
        "referred_count": referred_count,
        "paid_referrals": paid_count,
        "bonus_per_referral": REFERRAL_BONUS,
    }
