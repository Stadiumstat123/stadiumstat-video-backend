from .vision import load_models
if __name__ == '__main__':
    _, _, device, hashes = load_models(download=True)
    print('Prepared local OCR and detector weights for', device)
    for name, digest in hashes.items():
        print(name, digest)
