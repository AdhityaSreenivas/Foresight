import ast

def extract_functions(filename):
    with open(filename, 'r') as f:
        node = ast.parse(f.read())
    funcs = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
    print(f"{filename}: {funcs}")

extract_functions("apps/datasets/tasks.py")
extract_functions("apps/predictions/tasks.py")
extract_functions("ml_engine/training/trainer.py")
extract_functions("ml_engine/model_inference.py")
