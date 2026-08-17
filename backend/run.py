import uvicorn


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="localhost", port=5353, reload=True)
