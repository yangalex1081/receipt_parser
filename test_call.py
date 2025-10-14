import modal

fn = modal.Function.from_name("example-get-started","square")



# Call remote function with bytes
result = fn.remote(5)

print(result)
