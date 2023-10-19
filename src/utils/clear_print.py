def clear_print(value: object, flush=False):
    print('\033[F', end='\r')
    print('\033[K', end='\r')
    print(value, flush=flush)
