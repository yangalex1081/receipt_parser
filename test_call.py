import modal

fn = modal.Function.from_name("receipt-parsing-functions","test_hello")


print('test')
# Call remote function with bytes
result = fn.remote()
print('test2')
print(result)
