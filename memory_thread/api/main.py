from fastapi import FastAPI

app = FastAPI(
    title="Memory Thread Engine",
    description="API for the Memory Thread cognitive memory subsystem.",
    version="0.1.0",
)

@app.get("/")
def read_root():
    return {"status": "ok"}
