from fastapi import APIRouter, Depends
from core import db, get_current_user

router = APIRouter(prefix="/api")


@router.get("/stats/dashboard")
async def get_dashboard_stats(user: dict = Depends(get_current_user)):
    total_assignments = await db.assignments.count_documents({"user_id": user["id"]})
    completed_assignments = await db.assignments.count_documents({"user_id": user["id"], "status": "completed"})
    paid_assignments = await db.assignments.count_documents({"user_id": user["id"], "status": {"$in": ["paid", "completed"]}})

    pipeline = [
        {"$match": {"user_id": user["id"], "status": {"$in": ["paid", "completed"]}}},
        {"$group": {"_id": None, "total_words": {"$sum": "$word_count"}, "total_spent": {"$sum": "$final_price"}}},
    ]
    result = await db.assignments.aggregate(pipeline).to_list(1)

    total_words = result[0]["total_words"] if result else 0
    total_spent = result[0]["total_spent"] if result else 0

    return {
        "total_assignments": total_assignments,
        "completed_assignments": completed_assignments,
        "paid_assignments": paid_assignments,
        "total_words": total_words,
        "total_spent": round(total_spent, 2),
    }


@router.get("/")
async def root():
    return {"message": "Scholar Academic Writing Assistant API", "version": "1.0.0"}
