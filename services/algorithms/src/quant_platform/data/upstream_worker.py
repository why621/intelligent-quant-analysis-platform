"""Entry module kept separate from provider imports to avoid runpy re-imports."""
from quant_platform.data.upstream import main

if __name__ == "__main__":
    main()
