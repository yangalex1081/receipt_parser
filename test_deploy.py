import modal

app = modal.App("example-get-started")


@app.function()
def square(x):
    print("This code is running on a remote worker!")
    return x**2

