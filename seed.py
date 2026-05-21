import requests

products = [
    {
        "name": "Manzana Verde",
        "description": "Manzanas verdes frescas de granja, perfectas para repostería o snacks.",
        "price": 1500,
        "image_url": "🍏",
        "category": "frutas-verduras"
    },
    {
        "name": "Leche Entera",
        "description": "Leche entera fresca de vacas alimentadas con pasto.",
        "price": 2200,
        "image_url": "🥛",
        "category": "lacteos-huevos"
    },
    {
        "name": "Pan Casero",
        "description": "Delicioso pan casero horneado al momento.",
        "price": 3000,
        "image_url": "🍞",
        "category": "panaderia"
    },
    {
        "name": "Pollo Fresco",
        "description": "Pechugas de pollo frescas y limpias.",
        "price": 5500,
        "image_url": "🍗",
        "category": "carnes-pescados"
    },
    {
        "name": "Zanahorias Orgánicas",
        "description": "Zanahorias frescas de cultivo orgánico.",
        "price": 1200,
        "image_url": "🥕",
        "category": "frutas-verduras"
    }
]

for product in products:
    response = requests.post("http://localhost:8001/products", json=product)
    if response.status_code == 200:
        print(f"Added: {product['name']}")
    else:
        print(f"Failed to add {product['name']}: {response.text}")
