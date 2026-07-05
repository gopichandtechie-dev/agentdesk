from google.cloud import firestore

db = firestore.Client()

print("Firestore client created")

collections = list(db.collections())

print(collections)