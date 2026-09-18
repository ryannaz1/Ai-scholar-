from fastapi import APIRouter, HTTPException, Body
from core import (
    calculate_price, PriceCalculation,
    PRICE_PER_PAGE, WORDS_PER_PAGE, BULK_DISCOUNT_THRESHOLD, BULK_DISCOUNT_RATE,
)

router = APIRouter(prefix="/api")


@router.post("/pricing/calculate", response_model=PriceCalculation)
async def calculate_pricing(word_count: int = Body(..., embed=True)):
    if word_count <= 0:
        raise HTTPException(status_code=400, detail="Word count must be positive")
    return calculate_price(word_count)


@router.get("/pricing/info")
async def get_pricing_info():
    return {
        "price_per_page": PRICE_PER_PAGE,
        "words_per_page": WORDS_PER_PAGE,
        "bulk_discount_threshold": BULK_DISCOUNT_THRESHOLD,
        "bulk_discount_rate": BULK_DISCOUNT_RATE * 100,
    }
