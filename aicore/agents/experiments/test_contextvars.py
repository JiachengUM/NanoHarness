import contextvars

from rich import print

def test_basic():

    var = contextvars.ContextVar('var')
    var.set('spam')
    print(var.get())  # 'spam'

    ctx = contextvars.copy_context()

    def main():
        # 'var' was set to 'spam' before
        # calling 'copy_context()' and 'ctx.run(main)', so:
        print(var.get())  # 'spam'
        print(ctx[var])  # 'spam'

        var.set('ham')

        # Now, after setting 'var' to 'ham':
        print(var.get())  # 'ham'
        print(ctx[var])  # 'ham'

    # Any changes that the 'main' function makes to 'var'
    # will be contained in 'ctx'.
    ctx.run(main)

    # The 'main()' function was run in the 'ctx' context,
    # so changes to 'var' are contained in it:
    print(ctx[var])  # 'ham'

    # However, outside of 'ctx', 'var' is still set to 'spam':
    print(var.get())  # 'spam'


def test_asyncio_basic():
    pass


if __name__ == "__main__":
    test_basic()