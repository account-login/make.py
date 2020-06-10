import contextlib
import io
import subprocess
import tempfile
import traceback

import gnu_make_parse

PASSES = FAILS = 0

@contextlib.contextmanager
def wrap_test():
    global PASSES, FAILS

    try:
        yield
        PASSES += 1
    except Exception:
        traceback.print_exc()
        FAILS += 1
        return

@wrap_test()
def test(text, vars=None):
    exp_stderr = None

    # Run the input through gnu_make_parse
    f = io.StringIO(text)
    ctx = gnu_make_parse.ParseContext()
    ctx.parse_file(f, 'test-file')

    for [k, v] in sorted(vars.items()):
        value = exc = None
        try:
            value = ctx.eval(ctx.variables[k])
        except Exception as e:
            exc = e

        if isinstance(v, type) and issubclass(v, Exception):
            assert exc is not None and isinstance(exc, v)
        else:
            assert exc is None and value == v, (k, value)

    with tempfile.NamedTemporaryFile(mode='wt') as f:
        # Collect input/expected output for make run
        f.write(text)
        f.write('\n')

        exp_stdout = []
        for [i, [k, v]] in enumerate(sorted(vars.items())):
            f.write('$(info %s="$(%s)")\n' % (k, k))

            if v == RecursionError:
                exp_stderr = exp_stderr or ('%s:%s: *** Recursive variable `%s\' references '
                        'itself (eventually).  Stop.\n' % (f.name, i+1, k)).encode()
            else:
                exp_stdout.append('%s="%s"\n' % (k, v))
        exp_stdout = ''.join(exp_stdout).encode()

        f.flush()

        # Run the input through make
        proc = subprocess.run(['make', '-f', f.name], capture_output=True)

        exp_stderr = exp_stderr or b'make: *** No targets.  Stop.\n'
        assert proc.stdout == exp_stdout, (proc.stdout, exp_stdout)
        assert proc.stderr == exp_stderr, (proc.stderr, exp_stderr)

def main():
    # Last newline gets trimmed from defines
    test('''define nl


endef''', vars={'nl': '\n'})

    # Space trimming
    test('''nothing :=
space := $(nothing) ''', vars={'space': ' '})

    # Recursive variable expansion
    test('''
x = $(y)
y = $(z)
z = abc''', vars={'x': 'abc'})

    # Detect infinite recursion
    test('x = $(x)', vars={'x': RecursionError})

    # Simple variable expansion
    test('''
x := a
y := $(x) b
x := c''', vars={'x': 'c', 'y': 'a b'})

    # Pattern substitution
    test('''
x := aa.o    ab.z    ba.o    bb.o
a := $(x:.o=.c)
b := $(x:%.o=%.c)
c := $(x:a%.o=%.c)
d := $(x:a%.o=a%.c)''', vars={
        'a': 'aa.c ab.z ba.c bb.c',
        'b': 'aa.c ab.z ba.c bb.c',
        'c': 'a.c ab.z ba.o bb.o',
        'd': 'aa.c ab.z ba.o bb.o',
    })

    # Function calls
    test('''
reverse = $(2) $(1)
var = $(call reverse,x,y)''', vars={'var': 'y x'})

    print('%s/%s tests passed.' % (PASSES, PASSES + FAILS))

if __name__ == '__main__':
    main()