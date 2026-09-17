import multiprocessing
import sys
if __name__ == '__main__':
    multiprocessing.freeze_support()
    if len(sys.argv) == 3 and sys.argv[1] == '--smoke-test':
        from frozen_smoke import run
        run(sys.argv[2])
    else:
        from desktop import main
        main()
