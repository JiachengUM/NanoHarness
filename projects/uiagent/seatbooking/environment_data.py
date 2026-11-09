class Restaurant(BaseModel):
    name: str
    address: str
    phone: str
    website: str
    email: str
    description: str
    image: str
    rating: float
    reviews: int
    price_level: int
    cuisine: str
    hours: str
    tags: list[str]


restaurant_data: list[] = [
    "北京xxx店"
    

]