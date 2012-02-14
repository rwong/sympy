"""
There are two types of functions:
1) defined function like exp or sin that has a name and body
   (in the sense that function can be evaluated).
    e = exp
2) undefined function with a name but no body. Undefined
   functions can be defined using a Function class as follows:
       f = Function('f')
   (the result will be a Function instance)
3) this isn't implemented yet: anonymous function or lambda function that has
   no name but has body with dummy variables. Examples of anonymous function
   creation:
       f = Lambda(x, exp(x)*x)
       f = Lambda(exp(x)*x) # free symbols of expr define the number of args
       f = Lambda(exp(x)*x)  # free symbols in the expression define the number
                             # of arguments
       f = exp * Lambda(x,x)
4) isn't implemented yet: composition of functions, like (sin+cos)(x), this
   works in sympy core, but needs to be ported back to SymPy.

    Examples
    ========

    >>> import sympy
    >>> f = sympy.Function("f")
    >>> from sympy.abc import x
    >>> f(x)
    f(x)
    >>> print sympy.srepr(f(x).func)
    Function('f')
    >>> f(x).args
    (x,)

"""
from core import BasicMeta, C
from assumptions import WithAssumptions
from basic import Basic
from singleton import S
from expr import Expr, AtomicExpr
from decorators import _sympifyit, deprecated
from compatibility import iterable,is_sequence
from cache import cacheit
from numbers import Rational, Float

from sympy.core.containers import Tuple, Dict
from sympy.utilities import default_sort_key
from sympy.utilities.iterables import uniq

from sympy import mpmath
import sympy.mpmath.libmp as mlib

def _coeff_isneg(a):
    """Return True if the leading Number is negative.

    Examples
    ========

    >>> from sympy.core.function import _coeff_isneg
    >>> from sympy import S, Symbol, oo, pi
    >>> _coeff_isneg(-3*pi)
    True
    >>> _coeff_isneg(S(3))
    False
    >>> _coeff_isneg(-oo)
    True
    >>> _coeff_isneg(Symbol('n', negative=True)) # coeff is 1
    False

    """

    if a.is_Mul:
        a = a.args[0]
    return a.is_Number and a.is_negative

class PoleError(Exception):
    pass

class ArgumentIndexError(ValueError):
    def __str__(self):
        return ("Invalid operation with argument number %s for Function %s" %
                        (self.args[1], self.args[0]))

class FunctionClass(WithAssumptions):
    """
    Base class for function classes. FunctionClass is a subclass of type.

    Use Function('<function name>' [ , signature ]) to create
    undefined function classes.
    """
    __metaclass__ = BasicMeta

    _new = type.__new__

    def __repr__(cls):
        return cls.__name__

    @deprecated
    def __contains__(self, obj):
        return (self == obj)

class Application(Basic):
    """
    Base class for applied functions.

    Instances of Application represent the result of applying an application of
    any type to any object.
    """
    __metaclass__ = FunctionClass
    __slots__ = []

    is_Function = True

    nargs = None

    @cacheit
    def __new__(cls, *args, **options):
        args = map(sympify, args)

        # these lines should be refactored
        for opt in ["nargs", "dummy", "comparable", "noncommutative",
                    "commutative"]:
            if opt in options:
                del options[opt]

        if options.pop('evaluate', True):
            evaluated = cls.eval(*args)
            if evaluated is not None:
                return evaluated
        return super(Application, cls).__new__(cls, *args, **options)

    @classmethod
    def eval(cls, *args):
        """
        Returns a canonical form of cls applied to arguments args.

        The eval() method is called when the class cls is about to be
        instantiated and it should return either some simplified instance
        (possible of some other class), or if the class cls should be
        unmodified, return None.

        Examples of eval() for the function "sign"
        ---------------------------------------------

        @classmethod
        def eval(cls, arg):
            if arg is S.NaN:
                return S.NaN
            if arg is S.Zero: return S.Zero
            if arg.is_positive: return S.One
            if arg.is_negative: return S.NegativeOne
            if isinstance(arg, C.Mul):
                coeff, terms = arg.as_coeff_Mul(rational=True)
                if coeff is not S.One:
                    return cls(coeff) * cls(terms)

        """
        return

    @property
    def func(self):
        return self.__class__

    def _eval_subs(self, old, new):
        if self == old:
            return new
        elif old.is_Function and new.is_Function:
            if old == self.func:
                nargs = len(self.args)
                if (nargs == new.nargs or new.nargs is None or
                        (isinstance(new.nargs, tuple) and nargs in new.nargs)):
                    return new(*self.args)
        return self.func(*[s.subs(old, new) for s in self.args])

    @deprecated
    def __contains__(self, obj):
        if self.func == obj:
            return True
        return super(Application, self).__contains__(obj)


class Function(Application, Expr):
    """
    Base class for applied numeric functions.
    Constructor of undefined function classes.

    """

    @property
    def _diff_wrt(self):
        """Allow derivatives wrt functions.

        Examples
        ========

            >>> from sympy import Function, Symbol
            >>> f = Function('f')
            >>> x = Symbol('x')
            >>> f(x)._diff_wrt
            True
        """
        return True

    @cacheit
    def __new__(cls, *args, **options):
        # Handle calls like Function('f')
        if cls is Function:
            return UndefinedFunction(*args)

        if cls.nargs is not None:
            if isinstance(cls.nargs, tuple):
                nargs = cls.nargs
            else:
                nargs = (cls.nargs,)

            n = len(args)

            if n not in nargs:
                # XXX: exception message must be in exactly this format to make
                # it work with NumPy's functions like vectorize(). The ideal
                # solution would be just to attach metadata to the exception
                # and change NumPy to take advantage of this.
                temp = ('%(name)s takes exactly %(args)s '
                       'argument%(plural)s (%(given)s given)')
                raise TypeError(temp %
                    {
                    'name': cls,
                    'args': cls.nargs,
                    'plural': 's'*(n != 1),
                    'given': n})

        args = map(sympify, args)
        evaluate = options.pop('evaluate', True)
        if evaluate:
            evaluated = cls.eval(*args)
            if evaluated is not None:
                return evaluated
        result = super(Application, cls).__new__(cls, *args, **options)
        pr = max(cls._should_evalf(a) for a in args)
        pr2 = min(cls._should_evalf(a) for a in args)
        if evaluate and pr2 > 0:
            return result.evalf(mlib.libmpf.prec_to_dps(pr))
        return result

    @classmethod
    def _should_evalf(cls, arg):
        """
        Decide if the function should automatically evalf().

        By default (in this implementation), this happens if (and only if) the
        ARG is a floating point number.
        This function is used by __new__.
        """
        if arg.is_Float:
            return arg._prec
        if not arg.is_Add:
            return -1
        re, im = arg.as_real_imag()
        l = [a._prec for a in [re, im] if a.is_Float]
        l.append(-1)
        return max(l)

    @classmethod
    def class_key(cls):
        funcs = {
            'exp': 10,
            'log': 11,
            'sin': 20,
            'cos': 21,
            'tan': 22,
            'cot': 23,
            'sinh': 30,
            'cosh': 31,
            'tanh': 32,
            'coth': 33,
            'conjugate': 40,
            're': 41,
            'im': 42,
            'arg': 43,
        }
        name = cls.__name__

        try:
            i = funcs[name]
        except KeyError:
            nargs = cls.nargs

            i = 0 if nargs is None else 10000

        return 4, i, name


    @property
    def is_commutative(self):
        """
        Returns whether the functon is commutative.
        """
        if all(getattr(t, 'is_commutative') for t in self.args):
            return True
        else:
            return False

    def _eval_evalf(self, prec):
        # Lookup mpmath function based on name
        fname = self.func.__name__
        try:
            if not hasattr(mpmath, fname):
                from sympy.utilities.lambdify import MPMATH_TRANSLATIONS
                fname = MPMATH_TRANSLATIONS[fname]
            func = getattr(mpmath, fname)
        except (AttributeError, KeyError):
            try:
                return C.Float(self._imp_(*self.args), prec)
            except (AttributeError, TypeError):
                return

        # Convert all args to mpf or mpc
        try:
            args = [arg._to_mpmath(prec) for arg in self.args]
        except ValueError:
            return

        # Set mpmath precision and apply. Make sure precision is restored
        # afterwards
        orig = mpmath.mp.prec
        try:
            mpmath.mp.prec = prec
            v = func(*args)
        finally:
            mpmath.mp.prec = orig

        return Expr._from_mpmath(v, prec)

    def _eval_is_comparable(self):
        if self.is_Function:
            r = True
            for s in self.args:
                c = s.is_comparable
                if c is None:
                    return
                if not c:
                    r = False
            return r
        return

    def _eval_derivative(self, s):
        # f(x).diff(s) -> x.diff(s) * f.fdiff(1)(s)
        i = 0
        l = []
        for a in self.args:
            i += 1
            da = a.diff(s)
            if da is S.Zero:
                continue
            try:
                df = self.fdiff(i)
            except ArgumentIndexError:
                df = Function.fdiff(self, i)
            l.append(df * da)
        return Add(*l)

    def _eval_is_commutative(self):
        r = True
        for a in self._args:
            c = a.is_commutative
            if c is None:
                return None
            if not c:
                r = False
        return r

    def as_base_exp(self):
        """
        Returns the method as the 2-tuple (base, exponent).
        """
        return self, S.One

    def _eval_aseries(self, n, args0, x, logx):
        """
        Compute an asymptotic expansion around args0, in terms of self.args.
        This function is only used internally by _eval_nseries and should not
        be called directly; derived classes can overwrite this to implement
        asymptotic expansions.
        """
        from sympy.utilities.misc import filldedent
        raise PoleError(filldedent('''
            Asymptotic expansion of %s around %s is
            not implemented.''' % (type(self), args0)))

    def _eval_nseries(self, x, n, logx):
        """
        This function does compute series for multivariate functions,
        but the expansion is always in terms of *one* variable.
        Examples
        ========

        >>> from sympy import atan2, O
        >>> from sympy.abc import x, y
        >>> atan2(x, y).series(x, n=2)
        atan2(0, y) + x/y + O(x**2)
        >>> atan2(x, y).series(y, n=2)
        -y/x + atan2(x, 0) + O(y**2)

        This function also computes asymptotic expansions, if necessary
        and possible:

        >>> from sympy import loggamma
        >>> loggamma(1/x)._eval_nseries(x,0,None)
        -1/x - log(x)/x + log(x)/2 + O(1)

        """
        if self.func.nargs is None:
            from sympy.utilities.misc import filldedent
            raise NotImplementedError(filldedent('''
                series for user-defined functions are not
                supported.'''))
        args = self.args
        args0 = [t.limit(x, 0) for t in args]
        if any(t.is_bounded == False for t in args0):
            from sympy import oo, zoo, nan
            a = [t.compute_leading_term(x, logx=logx) for t in args]
            a0 = [t.limit(x, 0) for t in a]
            if any ([t.has(oo, -oo, zoo, nan) for t in a0]):
                return self._eval_aseries(n, args0, x, logx
                                          )._eval_nseries(x, n, logx)
            # Careful: the argument goes to oo, but only logarithmically so. We
            # are supposed to do a power series expansion "around the
            # logarithmic term". e.g.
            #      f(1+x+log(x))
            #     -> f(1+logx) + x*f'(1+logx) + O(x**2)
            # where 'logx' is given in the argument
            a = [t._eval_nseries(x, n, logx) for t in args]
            z = [r - r0 for (r, r0) in zip(a, a0)]
            p = [Dummy() for t in z]
            q = []
            v = None
            for ai, zi, pi in zip(a0, z, p):
                if zi.has(x):
                    if v is not None:
                        raise NotImplementedError
                    q.append(ai + pi)
                    v = pi
                else:
                    q.append(ai)
            e1 = self.func(*q)
            if v is None:
                return e1
            s = e1._eval_nseries(v, n, logx)
            o = s.getO()
            s = s.removeO()
            s = s.subs(v, zi).expand() + C.Order(o.expr.subs(v, zi), x)
            return s
        if (self.func.nargs == 1 and args0[0]) or self.func.nargs > 1:
            e = self
            e1 = e.expand()
            if e == e1:
                #for example when e = sin(x+1) or e = sin(cos(x))
                #let's try the general algorithm
                term = e.subs(x, S.Zero)
                if term.is_bounded is False or term is S.NaN:
                    raise PoleError("Cannot expand %s around 0" % (self))
                series = term
                fact = S.One
                for i in range(n-1):
                    i += 1
                    fact *= Rational(i)
                    e = e.diff(x)
                    subs = e.subs(x, S.Zero)
                    if subs is S.NaN:
                        # try to evaluate a limit if we have to
                        subs = e.limit(x, S.Zero)
                    if subs.is_bounded is False:
                        raise PoleError("Cannot expand %s around 0" % (self))
                    term = subs*(x**i)/fact
                    term = term.expand()
                    series += term
                return series + C.Order(x**n, x)
            return e1.nseries(x, n=n, logx=logx)
        arg = self.args[0]
        l = []
        g = None
        for i in xrange(n+2):
            g = self.taylor_term(i, arg, g)
            g = g.nseries(x, n=n, logx=logx)
            l.append(g)
        return Add(*l) + C.Order(x**n, x)

    def _eval_expand_basic(self, deep=True, **hints):
        if not deep:
            return self
        sargs, terms = self.args, []
        for term in sargs:
            if hasattr(term, '_eval_expand_basic'):
                newterm = term._eval_expand_basic(deep=deep, **hints)
            else:
                newterm = term
            terms.append(newterm)
        return self.func(*terms)

    def _eval_expand_power_exp(self, deep=True, **hints):
        if not deep:
            return self
        sargs, terms = self.args, []
        for term in sargs:
            if hasattr(term, '_eval_expand_power_exp'):
                newterm = term._eval_expand_power_exp(deep=deep, **hints)
            else:
                newterm = term
            terms.append(newterm)
        return self.func(*terms)

    def _eval_expand_power_base(self, deep=True, **hints):
        if not deep:
            return self
        sargs, terms = self.args, []
        for term in sargs:
            if hasattr(term, '_eval_expand_power_base'):
                newterm = term._eval_expand_power_base(deep=deep, **hints)
            else:
                newterm = term
            terms.append(newterm)
        return self.func(*terms)

    def _eval_expand_mul(self, deep=True, **hints):
        if not deep:
            return self
        sargs, terms = self.args, []
        for term in sargs:
            if hasattr(term, '_eval_expand_mul'):
                newterm = term._eval_expand_mul(deep=deep, **hints)
            else:
                newterm = term
            terms.append(newterm)
        return self.func(*terms)

    def _eval_expand_multinomial(self, deep=True, **hints):
        if not deep:
            return self
        sargs, terms = self.args, []
        for term in sargs:
            if hasattr(term, '_eval_expand_multinomail'):
                newterm = term._eval_expand_multinomial(deep=deep, **hints)
            else:
                newterm = term
            terms.append(newterm)
        return self.func(*terms)

    def _eval_expand_log(self, deep=True, **hints):
        if not deep:
            return self
        sargs, terms = self.args, []
        for term in sargs:
            if hasattr(term, '_eval_expand_log'):
                newterm = term._eval_expand_log(deep=deep, **hints)
            else:
                newterm = term
            terms.append(newterm)
        return self.func(*terms)

    def _eval_expand_complex(self, deep=True, **hints):
        if deep:
            func = self.func(*[ a.expand(deep, **hints) for a in self.args ])
        else:
            func = self.func(*self.args)
        return C.re(func) + S.ImaginaryUnit * C.im(func)

    def _eval_expand_trig(self, deep=True, **hints):
        sargs, terms = self.args, []
        for term in sargs:
            if hasattr(term, '_eval_expand_trig'):
                newterm = term._eval_expand_trig(deep=deep, **hints)
            else:
                newterm = term
            terms.append(newterm)
        return self.func(*terms)

    def _eval_expand_func(self, deep=True, **hints):
        sargs, terms = self.args, []
        for term in sargs:
            if hasattr(term, '_eval_expand_func'):
                newterm = term._eval_expand_func(deep=deep, **hints)
            else:
                newterm = term
            terms.append(newterm)
        return self.func(*terms)

    def _eval_rewrite(self, pattern, rule, **hints):
        if hints.get('deep', False):
            args = [a._eval_rewrite(pattern, rule, **hints) for a in self.args]
        else:
            args = self.args

        if pattern is None or isinstance(self.func, pattern):
            if hasattr(self, rule):
                rewritten = getattr(self, rule)(*args)

                if rewritten is not None:
                    return rewritten

        return self.func(*args)

    def fdiff(self, argindex=1):
        """
        Returns the first derivative of the function.
        """
        if self.nargs is not None:
            if isinstance(self.nargs, tuple):
                nargs = self.nargs[-1]
            else:
                nargs = self.nargs
            if not (1<=argindex<=nargs):
                raise ArgumentIndexError(self, argindex)
        if not self.args[argindex-1]._diff_wrt:
            # See issue 1525 and issue 1620 and issue 2501
            arg_dummy = C.Dummy('xi_%i' % argindex)
            return Subs(Derivative(
                self.subs(self.args[argindex-1], arg_dummy),
                arg_dummy), arg_dummy, self.args[argindex-1])
        return Derivative(self,self.args[argindex-1],evaluate=False)

    def _eval_as_leading_term(self, x):
        """General method for the leading term"""
        # XXX This seems broken to me!
        arg = self.args[0].as_leading_term(x)

        if C.Order(1,x).contains(arg):
            return arg
        else:
            return self.func(arg)

    @classmethod
    def taylor_term(cls, n, x, *previous_terms):
        """General method for the taylor term.

        This method is slow, because it differentiates n-times. Subclasses can
        redefine it to make it faster by using the "previous_terms".
        """
        x = sympify(x)
        return cls(x).diff(x, n).subs(x, 0) * x**n / C.factorial(n)


class AppliedUndef(Function):
    """
    Base class for expressions resulting from the application of an undefined
    function.
    """
    def __new__(cls, *args, **options):
        args = map(sympify, args)
        result = Expr.__new__(cls, *args, **options)
        result.nargs = len(args)
        return result

class UndefinedFunction(FunctionClass):
    """
    The (meta)class of undefined functions.
    """
    def __new__(mcl, name):
        return BasicMeta.__new__(mcl, name, (AppliedUndef,), {})


class WildFunction(Function, AtomicExpr):
    """
    WildFunction() matches any expression but another WildFunction()
    XXX is this as intended, does it work ?
    """

    nargs = 1

    def __new__(cls, name, **assumptions):
        obj = Function.__new__(cls, name, **assumptions)
        obj.name = name
        return obj

    def matches(self, expr, repl_dict={}):
        if self.nargs is not None:
            if not hasattr(expr,'nargs') or self.nargs != expr.nargs:
                return None
        repl_dict = repl_dict.copy()
        repl_dict[self] = expr
        return repl_dict

    @property
    def is_number(self):
        return False

class Derivative(Expr):
    """
    Carries out differentiation of the given expression with respect to symbols.

    expr must define ._eval_derivative(symbol) method that returns
    the differentiation result. This function only needs to consider the
    non-trivial case where expr contains symbol and it should call the diff()
    method internally (not _eval_derivative); Derivative should be the only
    one to call _eval_derivative.

    Ordering of variables:

    If evaluate is set to True and the expression can not be evaluated, the
    list of differentiation symbols will be sorted, that is, the expression is
    assumed to have continuous derivatives up to the order asked. This sorting
    assumes that derivatives wrt Symbols commute, derivatives wrt non-Symbols
    commute, but Symbol and non-Symbol derivatives don't commute with each
    other.

    Derivative wrt non-Symbols:

    This class also allows derivatives wrt non-Symbols that have _diff_wrt
    set to True, such as Function and Derivative. When a derivative wrt a non-
    Symbol is attempted, the non-Symbol is temporarily converted to a Symbol
    while the differentiation is performed.

    Note that this may seem strange, that Derivative allows things like
    f(g(x)).diff(g(x)), or even f(cos(x)).diff(cos(x)).  The motivation for
    allowing this syntax is to make it easier to work with variational calculus
    (i.e., the Euler-Lagrange method).  The best way to understand this is that
    the action of derivative with respect to a non-Symbol is defined by the
    above description:  the object is substituted for a Symbol and the
    derivative is taken with respect to that.  This action is only allowed for
    objects for which this can be done unambiguously, for example Function and
    Derivative objects.  Note that this leads to what may appear to be
    mathematically inconsistent results.  For example::

        >>> from sympy import cos, sin, sqrt
        >>> from sympy.abc import x
        >>> (2*cos(x)).diff(cos(x))
        2
        >>> (2*sqrt(1 - sin(x)**2)).diff(cos(x))
        0

    This appears wrong because in fact 2*cos(x) and 2*sqrt(1 - sin(x)**2) are
    identically equal.  However this is the wrong way to think of this.  Think
    of it instead as if we have something like this::

        >>> from sympy.abc import c, s
        >>> def F(u):
        ...     return 2*u
        ...
        >>> def G(u):
        ...     return 2*sqrt(1 - u**2)
        ...
        >>> F(cos(x))
        2*cos(x)
        >>> G(sin(x))
        2*sqrt(-sin(x)**2 + 1)
        >>> F(c).diff(c)
        2
        >>> F(c).diff(c)
        2
        >>> G(s).diff(c)
        0
        >>> G(sin(x)).diff(cos(x))
        0

    Here, the Symbols c and s act just like the functions cos(x) and sin(x),
    respectively. Think of 2*cos(x) as f(c).subs(c, cos(x)) (or f(c) *at*
    c = cos(x)) and 2*sqrt(1 - sin(x)**2) as g(s).subs(s, sin(x)) (or g(s) *at*
    s = sin(x)), where f(u) == 2*u and g(u) == 2*sqrt(1 - u**2).  Here, we
    define the function first and evaluate it at the function, but we can
    actually unambiguously do this in reverse in SymPy, because
    expr.subs(Function, Symbol) is well-defined:  just structurally replace the
    function everywhere it appears in the expression.

    This is actually the same notational convenience used in the Euler-Lagrange
    method when one says F(t, f(t), f'(t)).diff(f(t)).  What is actually meant
    is that the expression in question is represented by some F(t, u, v) at
    u = f(t) and v = f'(t), and F(t, f(t), f'(t)).diff(f(t)) simply means
    F(t, u, v).diff(u) at u = f(t).

    We do not allow to take derivative with respect to expressions where this
    is not so well defined.  For example, we do not allow expr.diff(x*y)
    because there are multiple ways of structurally defining where x*y appears
    in an expression, some of which may surprise the reader (for example, a
    very strict definition would have that (x*y*z).diff(x*y) == 0).

        >>> from sympy.abc import x, y, z
        >>> (x*y*z).diff(x*y)
        Traceback (most recent call last):
        ...
        ValueError: Can't differentiate wrt the variable: x*y, 1

    Note that this definition also fits in nicely with the definition of the
    chain rule.  Note how the chain rule in SymPy is defined using unevaluated
    Subs objects::

        >>> from sympy import symbols, Function
        >>> f, g = symbols('f g', cls=Function)
        >>> f(2*g(x)).diff(x)
        2*Derivative(g(x), x)*Subs(Derivative(f(_xi_1), _xi_1), (_xi_1,), (2*g(x),))

    This says that the derivative of f(2*g(x)) with respect to x is
    2*g(x).diff(x) times f(u).diff(u) at u = 2*g(x).  Note that this last part
    is exactly the same as our definition of a derivative with respect to a
    function given above, except the derivative is at a non-Function 2*g(x).
    If we instead computed f(g(x)).diff(x), we would be able to express the
    Subs as simply f(g(x)).diff(g(x)).  Therefore, SymPy does this when it's
    possible::

        >>> f(g(x)).diff(x)
        Derivative(f(g(x)), g(x))*Derivative(g(x), x)

    Finally, note that, to be consistent with variational calculus, and to
    ensure that the definition of substituting a Function for a Symbol in an
    expression is well-defined, derivatives of functions are assumed to not be
    related to the function.  In other words, we have::

        >>> from sympy import diff
        >>> diff(f(x), x).diff(f(x))
        0

    The same is actually true for derivatives of different orders::

        >>> diff(f(x), x, 2).diff(diff(f(x), x, 1))
        0
        >>> diff(f(x), x, 1).diff(diff(f(x), x, 2))
        0

    Note, any class can allow derivatives to be taken with respect to itself.
    See the docstring of Expr._diff_wrt.

    Examples
    ========

    Some basic examples:

        >>> from sympy import Derivative, Symbol, Function
        >>> f = Function('f')
        >>> g = Function('g')
        >>> x = Symbol('x')
        >>> y = Symbol('y')

        >>> Derivative(x**2, x, evaluate=True)
        2*x
        >>> Derivative(Derivative(f(x,y), x), y)
        Derivative(f(x, y), x, y)
        >>> Derivative(f(x), x, 3)
        Derivative(f(x), x, x, x)
        >>> Derivative(f(x, y), y, x, evaluate=True)
        Derivative(f(x, y), x, y)

    Now some derivatives wrt functions:

        >>> Derivative(f(x)**2, f(x), evaluate=True)
        2*f(x)
        >>> Derivative(f(g(x)), x, evaluate=True)
        Derivative(f(g(x)), g(x))*Derivative(g(x), x)
    """

    is_Derivative   = True

    @property
    def _diff_wrt(self):
        """Allow derivatives wrt Derivatives if it contains a function.

        Examples
        ========

            >>> from sympy import Function, Symbol, Derivative
            >>> f = Function('f')
            >>> x = Symbol('x')
            >>> Derivative(f(x),x)._diff_wrt
            True
            >>> Derivative(x**2,x)._diff_wrt
            False
        """
        if self.expr.is_Function:
            return True
        else:
            return False

    def __new__(cls, expr, *variables, **assumptions):
        expr = sympify(expr)

        # There are no variables, we differentiate wrt all of the free symbols
        # in expr.
        if not variables:
            variables = expr.free_symbols
            if len(variables) != 1:
                from sympy.utilities.misc import filldedent
                raise ValueError(filldedent('''
                    Since there is more than one variable in the
                    expression, the variable(s) of differentiation
                    must be supplied to differentiate %s''' % expr))

        # Standardize the variables by sympifying them and making appending a
        # count of 1 if there is only one variable: diff(e,x)->diff(e,x,1).
        variables = list(sympify(variables))
        if not variables[-1].is_Integer or len(variables) == 1:
            variables.append(S.One)

        # Split the list of variables into a list of the variables we are diff
        # wrt, where each element of the list has the form (s, count) where
        # s is the entity to diff wrt and count is the order of the
        # derivative.
        variable_count = []
        all_zero = True
        i = 0
        while i < len(variables) - 1: # process up to final Integer
            v, count = variables[i: i+2]
            iwas = i
            if v._diff_wrt:
                # We need to test the more specific case of count being an
                # Integer first.
                if count.is_Integer:
                    count = int(count)
                    i += 2
                elif count._diff_wrt:
                    count = 1
                    i += 1

            if i == iwas: # didn't get an update because of bad input
                from sympy.utilities.misc import filldedent
                raise ValueError(filldedent('''
                Can\'t differentiate wrt the variable: %s, %s''' % (v, count)))

            variable_count.append((v, count))

            if all_zero and not count == 0:
                all_zero = False

        # We make a special case for 0th derivative, because there is no
        # good way to unambiguously print this.
        if all_zero:
            return expr

        # Pop evaluate because it is not really an assumption and we will need
        # to track use it carefully below.
        evaluate = assumptions.pop('evaluate', False)

        # Look for a quick exit if there are symbols that don't appear in
        # expression at all. Note, this cannnot check non-symbols like
        # functions and Derivatives as those can be created by intermediate
        # derivatives.
        if evaluate:
            symbol_set = set(sc[0] for sc in variable_count if sc[0].is_Symbol)
            if symbol_set.difference(expr.free_symbols):
                return S.Zero

        # We make a generator so as to only generate a variable when necessary.
        # If a high order of derivative is requested and the expr becomes 0
        # after a few differentiations, then we won't need the other variables.
        variablegen = (v for v, count in variable_count for i in xrange(count))

        if expr.is_commutative:
            assumptions['commutative'] = True

        # If we can't compute the derivative of expr (but we wanted to) and
        # expr is itself not a Derivative, finish building an unevaluated
        # derivative class by calling Expr.__new__.
        if (not (hasattr(expr, '_eval_derivative') and evaluate) and
           (not isinstance(expr, Derivative))):
            variables = list(variablegen)
            # If we wanted to evaluate, we sort the variables into standard
            # order for later comparisons. This is too agressive if evaluate
            # is False, so we don't do it in that case.
            if evaluate:
                #TODO: check if assumption of discontinuous derivatives exist
                variables = cls._sort_variables(variables)
            # Here we *don't* need to reinject evaluate into assumptions
            # because we are done with it and it is not an assumption that
            # Expr knows about.
            obj = Expr.__new__(cls, expr, *variables, **assumptions)
            return obj

        # Compute the derivative now by repeatedly calling the
        # _eval_derivative method of expr for each variable. When this method
        # returns None, the derivative couldn't be computed wrt that variable
        # and we save the variable for later.
        unhandled_variables = []

        # Once we encouter a non_symbol that is unhandled, we stop taking
        # derivatives entirely. This is because derivatives wrt functions
        # don't commute with derivatives wrt symbols and we can't safely
        # continue.
        unhandled_non_symbol = False
        for v in variablegen:
            is_symbol = v.is_Symbol

            if unhandled_non_symbol:
                obj = None
            else:
                if not is_symbol:
                    new_v = C.Symbol('diff_wrt_%i' % i)
                    expr = expr.subs(v, new_v)
                    old_v = v
                    v = new_v
                obj = expr._eval_derivative(v)
                if not is_symbol:
                    if obj is not None:
                        obj = obj.subs(v, old_v)
                    v = old_v

            if obj is None:
                unhandled_variables.append(v)
                if not is_symbol:
                    unhandled_non_symbol = True
            elif obj is S.Zero:
                return S.Zero
            else:
                expr = obj

        if unhandled_variables:
            unhandled_variables = cls._sort_variables(unhandled_variables)
            expr = Expr.__new__(cls, expr, *unhandled_variables, **assumptions)
        else:
            # We got a Derivative at the end of it all, and we rebuild it by
            # sorting its variables.
            if isinstance(expr, Derivative):
                expr = Derivative(
                    expr.args[0], *cls._sort_variables(expr.args[1:])
                )

        return expr

    @classmethod
    def _sort_variables(cls, vars):
        """Sort variables, but disallow sorting of non-symbols.

        When taking derivatives, the following rules usually hold:

        * Derivative wrt different symbols commute.
        * Derivative wrt different non-symbols commute.
        * Derivatives wrt symbols and non-symbols dont' commute.

        Examples
        --------

        >>> from sympy import Derivative, Function, symbols
        >>> vsort = Derivative._sort_variables
        >>> x, y, z = symbols('x y z')
        >>> f, g, h = symbols('f g h', cls=Function)

        >>> vsort((x,y,z))
        [x, y, z]

        >>> vsort((h(x),g(x),f(x)))
        [f(x), g(x), h(x)]

        >>> vsort((z,y,x,h(x),g(x),f(x)))
        [x, y, z, f(x), g(x), h(x)]

        >>> vsort((x,f(x),y,f(y)))
        [x, f(x), y, f(y)]

        >>> vsort((y,x,g(x),f(x),z,h(x),y,x))
        [x, y, f(x), g(x), z, h(x), x, y]

        >>> vsort((z,y,f(x),x,f(x),g(x)))
        [y, z, f(x), x, f(x), g(x)]

        >>> vsort((z,y,f(x),x,f(x),g(x),z,z,y,x))
        [y, z, f(x), x, f(x), g(x), x, y, z, z]
        """

        sorted_vars = []
        symbol_part = []
        non_symbol_part = []
        for v in vars:
            if not v.is_Symbol:
                if len(symbol_part) > 0:
                    sorted_vars.extend(sorted(symbol_part,
                                              key=default_sort_key))
                    symbol_part = []
                non_symbol_part.append(v)
            else:
                if len(non_symbol_part) > 0:
                    sorted_vars.extend(sorted(non_symbol_part,
                                              key=default_sort_key))
                    non_symbol_part = []
                symbol_part.append(v)
        if len(non_symbol_part) > 0:
            sorted_vars.extend(sorted(non_symbol_part,
                                      key=default_sort_key))
        if len(symbol_part) > 0:
            sorted_vars.extend(sorted(symbol_part,
                                      key=default_sort_key))
        return sorted_vars

    def _eval_derivative(self, v):
        # If the variable s we are diff wrt is not in self.variables, we
        # assume that we might be able to take the derivative.
        if v not in self.variables:
            obj = self.expr.diff(v)
            if obj is S.Zero:
                return S.Zero
            if isinstance(obj, Derivative):
                return Derivative(obj.expr, *(self.variables + obj.variables))
            # The derivative wrt s could have simplified things such that the
            # derivative wrt things in self.variables can now be done. Thus,
            # we set evaluate=True to see if there are any other derivatives
            # that can be done. The most common case is when obj is a simple
            # number so that the derivative wrt anything else will vanish.
            return Derivative(obj, *self.variables, **{'evaluate': True})
        # In this case s was in self.variables so the derivatve wrt s has
        # already been attempted and was not computed, either because it
        # couldn't be or evaluate=False originally.
        return Derivative(self.expr, *(self.variables + (v, )),
                          **{'evaluate': False})

    def doit(self, **hints):
        expr = self.expr
        if hints.get('deep', True):
            expr = expr.doit(**hints)
        hints['evaluate'] = True
        return Derivative(expr, *self.variables, **hints)

    @_sympifyit('z0', NotImplementedError)
    def doit_numerically(self, z0):
        """
        Evaluate the derivative at z numerically.

        When we can represent derivatives at a point, this should be folded
        into the normal evalf. For now, we need a special method.
        """
        from sympy import mpmath
        from sympy.core.expr import Expr
        if len(self.free_symbols) != 1 or len(self.variables) != 1:
            raise NotImplementedError('partials and higher order derivatives')
        z = list(self.free_symbols)[0]
        def eval(x):
            f0 = self.expr.subs(z, Expr._from_mpmath(x, prec=mpmath.mp.prec))
            f0 = f0.evalf(mlib.libmpf.prec_to_dps(mpmath.mp.prec))
            return f0._to_mpmath(mpmath.mp.prec)
        return Expr._from_mpmath(mpmath.diff(eval,
                                             z0._to_mpmath(mpmath.mp.prec)),
                                 mpmath.mp.prec)

    @property
    def expr(self):
        return self._args[0]

    @property
    def variables(self):
        return self._args[1:]

    @property
    def free_symbols(self):
        return self.expr.free_symbols

    def _eval_subs(self, old, new):
        if self==old:
            return new
        # Subs should only be used in situations where new is not a valid
        # variable for differentiating wrt. Previously, Subs was used for
        # anything that was not a Symbol, but that was too broad.
        if old in self.variables and not new._diff_wrt:
            # Issue 1620
            return Subs(self, old, new)
        return Derivative(*map(lambda x: x._eval_subs(old, new), self.args))

    def _eval_lseries(self, x):
        dx = self.args[1:]
        for term in self.args[0].lseries(x):
            yield Derivative(term, *dx)

    def _eval_nseries(self, x, n, logx):
        arg = self.args[0].nseries(x, n=n, logx=logx)
        o = arg.getO()
        dx = self.args[1:]
        rv = [Derivative(a, *dx) for a in Add.make_args(arg.removeO())]
        if o:
            rv.append(o/x)
        return Add(*rv)

    def _eval_as_leading_term(self, x):
        return self.args[0].as_leading_term(x)

class Lambda(Expr):
    """
    Lambda(x, expr) represents a lambda function similar to Python's
    'lambda x: expr'. A function of several variables is written as
    Lambda((x, y, ...), expr).

    A simple example:

    >>> from sympy import Lambda
    >>> from sympy.abc import x
    >>> f = Lambda(x, x**2)
    >>> f(4)
    16

    For multivariate functions, use:

    >>> from sympy.abc import y, z, t
    >>> f2 = Lambda((x, y, z, t), x + y**z + t**z)
    >>> f2(1, 2, 3, 4)
    73

    A handy shortcut for lots of arguments:

    >>> p = x, y, z
    >>> f = Lambda(p, x + y*z)
    >>> f(*p)
    x + y*z

    """
    is_Function = True
    __slots__ = []

    def __new__(cls, variables, expr):
        try:
            variables = Tuple(*variables)
        except TypeError:
            variables = Tuple(variables)
        if len(variables) == 1 and variables[0] == expr:
            return S.IdentityFunction

        #use dummy variables internally, just to be sure
        new_variables = [C.Dummy(arg.name) for arg in variables]
        expr = sympify(expr).xreplace(dict(zip(variables, new_variables)))

        obj = Expr.__new__(cls, Tuple(*new_variables), expr)
        return obj

    @property
    def variables(self):
        """The variables used in the internal representation of the function"""
        return self._args[0]

    @property
    def expr(self):
        """The return value of the function"""
        return self._args[1]

    @property
    def free_symbols(self):
        return self.expr.free_symbols - set(self.variables)

    @property
    def nargs(self):
        """The number of arguments that this function takes"""
        return len(self._args[0])

    def __call__(self, *args):
        if len(args) != self.nargs:
            from sympy.utilities.misc import filldedent
            raise TypeError(filldedent('''
                %s takes %d arguments (%d given)
                ''' % (self, self.nargs, len(args))))
        return self.expr.xreplace(dict(zip(self.variables, args)))

    def __eq__(self, other):
        if not isinstance(other, Lambda):
            return False
        if self.nargs != other.nargs:
            return False

        selfexpr = self.args[1]
        otherexpr = other.args[1]
        otherexpr = otherexpr.xreplace(dict(zip(other.args[0], self.args[0])))
        return selfexpr == otherexpr

    def __ne__(self, other):
        return not(self == other)

    def __hash__(self):
        return super(Lambda, self).__hash__()

    def _hashable_content(self):
        return (self.nargs, ) + tuple(sorted(self.free_symbols))

    @property
    def is_identity(self):
        """Return ``True`` if this ``Lambda`` is an identity function. """
        if len(self.args) == 2:
            return self.args[0] == self.args[1]
        else:
            return None

class Subs(Expr):
    """
    Represents unevaluated substitutions of an expression.

    ``Subs(expr, x, x0)`` receives 3 arguments: an expression, a variable or
    list of distinct variables and a point or list of evaluation points
    corresponding to those variables.

    ``Subs`` objects are generally useful to represent unevaluated derivatives
    calculated at a point.

    The variables may be expressions, but they are subjected to the limitations
    of subs(), so it is usually a good practice to use only symbols for
    variables, since in that case there can be no ambiguity.

    There's no automatic expansion - use the method .doit() to effect all
    possible substitutions of the object and also of objects inside the
    expression.

    When evaluating derivatives at a point that is not a symbol, a Subs object
    is returned. One is also able to calculate derivatives of Subs objects - in
    this case the expression is always expanded (for the unevaluated form, use
    Derivative()).

    A simple example:

    >>> from sympy import Subs, Function, sin
    >>> from sympy.abc import x, y, z
    >>> f = Function('f')
    >>> e = Subs(f(x).diff(x), x, y)
    >>> e.subs(y, 0)
    Subs(Derivative(f(_x), _x), (_x,), (0,))
    >>> e.subs(f, sin).doit()
    cos(y)

    An example with several variables:

    >>> Subs(f(x)*sin(y)+z, (x, y), (0, 1))
    Subs(z + f(_x)*sin(_y), (_x, _y), (0, 1))
    >>> _.doit()
    z + f(0)*sin(1)

    """
    def __new__(cls, expr, variables, point, **assumptions):
        if not is_sequence(variables, Tuple):
            variables = [variables]
        variables = Tuple(*sympify(variables))

        if uniq(variables) != variables:
            repeated = repeated = [ v for v in set(variables)
                                    if list(variables).count(v) > 1 ]
            raise ValueError('cannot substitute expressions %s more than '
                             'once.' % repeated)

        if not is_sequence(point, Tuple):
            point = [point]
        point = Tuple(*sympify(point))

        if len(point) != len(variables):
            raise ValueError('Number of point values must be the same as '
                             'the number of variables.')

        # it's necessary to use dummy variables internally
        new_variables = Tuple(*[ arg.as_dummy() if arg.is_Symbol else
            C.Dummy(str(arg)) for arg in variables ])
        expr = sympify(expr).subs(tuple(zip(variables, new_variables)))

        if expr.is_commutative:
            assumptions['commutative'] = True

        obj = Expr.__new__(cls, expr, new_variables, point, **assumptions)
        return obj

    def doit(self):
        return self.expr.doit().subs(zip(self.variables, self.point))

    def evalf(self, prec=None, **options):
        if prec is None:
            return self.doit().evalf(**options)
        else:
            return self.doit().evalf(prec, **options)

    n = evalf

    @property
    def variables(self):
        """The variables to be evaluated"""
        return self._args[1]

    @property
    def expr(self):
        """The expression on which the substitution operates"""
        return self._args[0]

    @property
    def point(self):
        """The values for which the variables are to be substituted"""
        return self._args[2]

    @property
    def free_symbols(self):
        return (self.expr.free_symbols - set(self.variables) |
            set(self.point.free_symbols))

    def __eq__(self, other):
        if not isinstance(other, Subs):
            return False
        if (len(self.point) != len(other.point) or
            self.free_symbols != other.free_symbols or
            sorted(self.point) != sorted(other.point)):
            return False

        # non-repeated point args
        selfargs = [ v[0] for v in sorted(zip(self.variables, self.point),
            key = lambda v: v[1]) if list(self.point.args).count(v[1]) == 1 ]
        otherargs = [ v[0] for v in sorted(zip(other.variables, other.point),
            key = lambda v: v[1]) if list(other.point.args).count(v[1]) == 1 ]
        # find repeated point values and subs each associated variable
        # for a single symbol
        selfrepargs = []
        otherrepargs = []
        if uniq(self.point) != self.point:
            repeated = uniq([ v for v in self.point if
                                list(self.point.args).count(v) > 1 ])
            repswap = dict(zip(repeated, [ C.Dummy() for _ in
                                            xrange(len(repeated)) ]))
            selfrepargs = [ (self.variables[i], repswap[v]) for i, v in
                            enumerate(self.point) if v in repeated ]
            otherrepargs = [ (other.variables[i], repswap[v]) for i, v in
                            enumerate(other.point) if v in repeated ]

        return self.expr.subs(selfrepargs) == other.expr.subs(
                tuple(zip(otherargs, selfargs))).subs(otherrepargs)

    def __ne__(self, other):
        return not(self == other)

    def __hash__(self):
        return super(Subs, self).__hash__()

    def _hashable_content(self):
        return tuple(sorted(self.point)) + tuple(sorted(self.free_symbols))

    def _eval_subs(self, old, new):
        if self == old:
            return new
        return Subs(self.expr.subs(old, new), self.variables,
                    self.point.subs(old, new))

    def _eval_derivative(self, s):
        if s not in self.free_symbols:
            return S.Zero
        return Subs(self.expr.diff(s), self.variables, self.point).doit() \
                + Add(*[ Subs(point.diff(s) * self.expr.diff(arg),
                    self.variables, self.point).doit() for arg,
                    point in zip(self.variables, self.point) ])


def diff(f, *symbols, **kwargs):
    """
    Differentiate f with respect to symbols.

    This is just a wrapper to unify .diff() and the Derivative class; its
    interface is similar to that of integrate().  You can use the same
    shortcuts for multiple variables as with Derivative.  For example,
    diff(f(x), x, x, x) and diff(f(x), x, 3) both return the third derivative
    of f(x).

    You can pass evaluate=False to get an unevaluated Derivative class.  Note
    that if there are 0 symbols (such as diff(f(x), x, 0), then the result will
    be the function (the zeroth derivative), even if evaluate=False.

    Examples
    ========

    >>> from sympy import sin, cos, Function, diff
    >>> from sympy.abc import x, y
    >>> f = Function('f')

    >>> diff(sin(x), x)
    cos(x)
    >>> diff(f(x), x, x, x)
    Derivative(f(x), x, x, x)
    >>> diff(f(x), x, 3)
    Derivative(f(x), x, x, x)
    >>> diff(sin(x)*cos(y), x, 2, y, 2)
    sin(x)*cos(y)

    >>> type(diff(sin(x), x))
    cos
    >>> type(diff(sin(x), x, evaluate=False))
    <class 'sympy.core.function.Derivative'>
    >>> type(diff(sin(x), x, 0))
    sin
    >>> type(diff(sin(x), x, 0, evaluate=False))
    sin

    >>> diff(sin(x))
    cos(x)
    >>> diff(sin(x*y))
    Traceback (most recent call last):
    ...
    ValueError: specify differentiation variables to differentiate sin(x*y)

    Note that ``diff(sin(x))`` syntax is meant only for convenience
    in interactive sessions and should be avoided in library code.

    References
    ==========

    http://documents.wolfram.com/v5/Built-inFunctions/AlgebraicComputation/
           Calculus/D.html

    See Also
    ========

    Derivative

    """
    kwargs.setdefault('evaluate', True)
    return Derivative(f, *symbols, **kwargs)

def expand(e, deep=True, modulus=None, power_base=True, power_exp=True, \
        mul=True, log=True, multinomial=True, basic=True, **hints):
    """
    Expand an expression using methods given as hints.

    Hints are applied with arbitrary order so your code shouldn't
    depend on the way hints are passed to this method.

    Hints evaluated unless explicitly set to False are:
      basic, log, multinomial, mul, power_base, and power_exp
    The following hints are supported but not applied unless set to True:
      complex, func, trig, frac, numer, and denom.

    basic is a generic keyword for methods that want to be expanded
    automatically.  For example, Integral uses expand_basic to expand the
    integrand.  If you want your class expand methods to run automatically and
    they don't fit one of the already automatic methods, wrap it around
    _eval_expand_basic.

    If deep is set to True, things like arguments of functions are
    recursively expanded.  Use deep=False to only expand on the top
    level.

    If the 'force' hint is used, assumptions about variables will be ignored
    in making the expansion.

    Also see expand_log, expand_mul, separate, expand_complex, expand_trig,
    and expand_func, which are wrappers around those expansion methods.

    >>> from sympy import cos, exp
    >>> from sympy.abc import x, y, z

    mul - Distributes multiplication over addition:

    >>> (y*(x + z)).expand(mul=True)
    x*y + y*z

    complex - Split an expression into real and imaginary parts:

    >>> (x + y).expand(complex=True)
    re(x) + re(y) + I*im(x) + I*im(y)
    >>> cos(x).expand(complex=True)
    -I*sin(re(x))*sinh(im(x)) + cos(re(x))*cosh(im(x))

    power_exp - Expand addition in exponents into multiplied bases:

    >>> exp(x + y).expand(power_exp=True)
    exp(x)*exp(y)
    >>> (2**(x + y)).expand(power_exp=True)
    2**x*2**y

    power_base - Split powers of multiplied bases if assumptions allow
    or if the 'force' hint is used:

    >>> ((x*y)**z).expand(power_base=True)
    (x*y)**z
    >>> ((x*y)**z).expand(power_base=True, force=True)
    x**z*y**z
    >>> ((2*y)**z).expand(power_base=True)
    2**z*y**z

    log - Pull out power of an argument as a coefficient and split logs products
    into sums of logs.  Note that these only work if the arguments of the log
    function have the proper assumptions: the arguments must be positive and the
    exponents must be real or else the force hint must be True:

    >>> from sympy import log, symbols, oo
    >>> log(x**2*y).expand(log=True)
    log(x**2*y)
    >>> log(x**2*y).expand(log=True, force=True)
    2*log(x) + log(y)
    >>> x, y = symbols('x,y', positive=True)
    >>> log(x**2*y).expand(log=True)
    2*log(x) + log(y)

    trig - Do trigonometric expansions:

    >>> cos(x + y).expand(trig=True)
    -sin(x)*sin(y) + cos(x)*cos(y)

    func - Expand other functions:

    >>> from sympy import gamma
    >>> gamma(x + 1).expand(func=True)
    x*gamma(x)

    multinomial - Expand (x + y + ...)**n where n is a positive integer:

    >>> ((x + y + z)**2).expand(multinomial=True)
    x**2 + 2*x*y + 2*x*z + y**2 + 2*y*z + z**2

    You can shut off methods that you don't want:

    >>> (exp(x + y)*(x + y)).expand()
    x*exp(x)*exp(y) + y*exp(x)*exp(y)
    >>> (exp(x + y)*(x + y)).expand(power_exp=False)
    x*exp(x + y) + y*exp(x + y)
    >>> (exp(x + y)*(x + y)).expand(mul=False)
    (x + y)*exp(x)*exp(y)

    Use deep=False to only expand on the top level:

    >>> exp(x + exp(x + y)).expand()
    exp(x)*exp(exp(x)*exp(y))
    >>> exp(x + exp(x + y)).expand(deep=False)
    exp(x)*exp(exp(x + y))

    Note: because hints are applied in arbitrary order, some hints may
    prevent expansion by other hints if they are applied first.  In
    particular, mul may distribute multiplications and prevent log and
    power_base from expanding them.  Also, if mul is applied before multinomial,
    the expression might not be fully distributed.  The solution is to expand
    with mul=False first, then run expand_mul if you need further expansion.

    Examples
    ========

    >>> from sympy import expand_log, expand, expand_mul
    >>> x, y, z = symbols('x,y,z', positive=True)

    ::

      expand(log(x*(y + z))) # could be either one below
      log(x*y + x*z)
      log(x) + log(y + z)

    >>> expand_log(log(x*y + x*z))
    log(x*y + x*z)

    >>> expand(log(x*(y + z)), mul=False)
    log(x) + log(y + z)

    ::

      expand((x*(y + z))**x) # could be either one below
      (x*y + x*z)**x
      x**x*(y + z)**x

    >>> expand((x*(y + z))**x, mul=False)
    x**x*(y + z)**x

    ::

      expand(x*(y + z)**2) # could be either one below
      2*x*y*z + x*y**2 + x*z**2
      x*(y + z)**2

    >>> expand(x*(y + z)**2, mul=False)
    x*(y**2 + 2*y*z + z**2)

    >>> expand_mul(_)
    x*y**2 + 2*x*y*z + x*z**2

    >>> expand((x + y)*y/x)
    y + y**2/x

    The parts of a rational expression can be targeted, too:

    >>> expand((x + y)*y/x/(x + 1), frac=True)
    (x*y + y**2)/(x**2 + x)
    >>> expand((x + y)*y/x/(x + 1), numer=True)
    (x*y + y**2)/(x*(x + 1))
    >>> expand((x + y)*y/x/(x + 1), denom=True)
    y*(x + y)/(x**2 + x)
    """
    # don't modify this; modify the Expr.expand method
    hints['power_base'] = power_base
    hints['power_exp'] = power_exp
    hints['mul'] = mul
    hints['log'] = log
    hints['multinomial'] = multinomial
    hints['basic'] = basic
    return sympify(e).expand(deep=deep, modulus=modulus, **hints)

# These are simple wrappers around single hints.  Feel free to add ones for
# power_exp, power_base, multinomial, or basic if you need them.
def expand_mul(expr, deep=True):
    """
    Wrapper around expand that only uses the mul hint.  See the expand
    docstring for more information.

    Examples
    ========

    >>> from sympy import symbols, expand_mul, exp, log
    >>> x, y = symbols('x,y', positive=True)
    >>> expand_mul(exp(x+y)*(x+y)*log(x*y**2))
    x*exp(x + y)*log(x*y**2) + y*exp(x + y)*log(x*y**2)

    """
    return sympify(expr).expand(deep=deep, mul=True, power_exp=False,\
    power_base=False, basic=False, multinomial=False, log=False)

def expand_multinomial(expr, deep=True):
    """
    Wrapper around expand that only uses the multinomial hint.  See the expand
    docstring for more information.

    Examples
    ========

    >>> from sympy import symbols, expand_multinomial, exp
    >>> x, y = symbols('x y', positive=True)
    >>> expand_multinomial((x + exp(x + 1))**2)
    x**2 + 2*x*exp(x + 1) + exp(2*x + 2)

    """
    return sympify(expr).expand(deep=deep, mul=False, power_exp=False,\
    power_base=False, basic=False, multinomial=True, log=False)


def expand_log(expr, deep=True):
    """
    Wrapper around expand that only uses the log hint.  See the expand
    docstring for more information.

    Examples
    ========

    >>> from sympy import symbols, expand_log, exp, log
    >>> x, y = symbols('x,y', positive=True)
    >>> expand_log(exp(x+y)*(x+y)*log(x*y**2))
    (x + y)*(log(x) + 2*log(y))*exp(x + y)

    """
    return sympify(expr).expand(deep=deep, log=True, mul=False,\
    power_exp=False, power_base=False, multinomial=False, basic=False)

def expand_func(expr, deep=True):
    """
    Wrapper around expand that only uses the func hint.  See the expand
    docstring for more information.

    Examples
    ========

    >>> from sympy import expand_func, gamma
    >>> from sympy.abc import x
    >>> expand_func(gamma(x + 2))
    x*(x + 1)*gamma(x)

    """
    return sympify(expr).expand(deep=deep, func=True, basic=False,\
    log=False, mul=False, power_exp=False, power_base=False, multinomial=False)

def expand_trig(expr, deep=True):
    """
    Wrapper around expand that only uses the trig hint.  See the expand
    docstring for more information.

    Examples
    ========

    >>> from sympy import expand_trig, sin, cos
    >>> from sympy.abc import x, y
    >>> expand_trig(sin(x+y)*(x+y))
    (x + y)*(sin(x)*cos(y) + sin(y)*cos(x))

    """
    return sympify(expr).expand(deep=deep, trig=True, basic=False,\
    log=False, mul=False, power_exp=False, power_base=False, multinomial=False)

def expand_complex(expr, deep=True):
    """
    Wrapper around expand that only uses the complex hint.  See the expand
    docstring for more information.

    Examples
    ========

    >>> from sympy import expand_complex, I, im, re
    >>> from sympy.abc import z
    >>> expand_complex(z**(2*I))
    re(z**(2*I)) + I*im(z**(2*I))

    """
    return sympify(expr).expand(deep=deep, complex=True, basic=False,\
    log=False, mul=False, power_exp=False, power_base=False, multinomial=False)

def expand_power_base(expr, deep=True):
    """
    Wrapper around expand that only uses the power_base hint.

    See the expand docstring for more information.

    Examples
    ========

    >>> from sympy import expand_power_base
    >>> from sympy.abc import x, y
    >>> expand_power_base((3*x)**y)
    3**y*x**y
    """
    return sympify(expr).expand(deep=deep, complex=False, basic=False,\
    log=False, mul=False, power_exp=False, power_base=True, multinomial=False)

def count_ops(expr, visual=False):
    """
    Return a representation (integer or expression) of the operations in expr.

    If ``visual`` is ``False`` (default) then the sum of the coefficients of the
    visual expression will be returned.

    If ``visual`` is ``True`` then the number of each type of operation is shown
    with the core class types (or their virtual equivalent) multiplied by the
    number of times they occur.

    If expr is an iterable, the sum of the op counts of the
    items will be returned.

    Examples
    ========

    >>> from sympy.abc import a, b, x, y
    >>> from sympy import sin, count_ops

    Although there isn't a SUB object, minus signs are interpreted as
    either negations or subtractions:

    >>> (x - y).count_ops(visual=True)
    SUB
    >>> (-x).count_ops(visual=True)
    NEG

    Here, there are two Adds and a Pow:

    >>> (1 + a + b**2).count_ops(visual=True)
    2*ADD + POW

    In the following, an Add, Mul, Pow and two functions:

    >>> (sin(x)*x + sin(x)**2).count_ops(visual=True)
    ADD + MUL + POW + 2*SIN

    for a total of 5:

    >>> (sin(x)*x + sin(x)**2).count_ops(visual=False)
    5

    Note that "what you type" is not always what you get. The expression
    1/x/y is translated by sympy into 1/(x*y) so it gives a DIV and MUL rather
    than two DIVs:

    >>> (1/x/y).count_ops(visual=True)
    DIV + MUL

    The visual option can be used to demonstrate the difference in
    operations for expressions in different forms. Here, the Horner
    representation is compared with the expanded form of a polynomial:

    >>> eq=x*(1 + x*(2 + x*(3 + x)))
    >>> count_ops(eq.expand(), visual=True) - count_ops(eq, visual=True)
    -MUL + 3*POW

    The count_ops function also handles iterables:

    >>> count_ops([x, sin(x), None, True, x + 2], visual=False)
    2
    >>> count_ops([x, sin(x), None, True, x + 2], visual=True)
    ADD + SIN
    >>> count_ops({x: sin(x), x + 2: y + 1}, visual=True)
    2*ADD + SIN

    """
    from sympy.simplify.simplify import fraction

    expr = sympify(expr)
    if isinstance(expr, Expr):

        ops = []
        args = [expr]
        NEG = C.Symbol('NEG')
        DIV = C.Symbol('DIV')
        SUB = C.Symbol('SUB')
        ADD = C.Symbol('ADD')
        while args:
            a = args.pop()
            if a.is_Rational:
                #-1/3 = NEG + DIV
                if a is not S.One:
                    if a.p < 0:
                        ops.append(NEG)
                    if a.q != 1:
                        ops.append(DIV)
                    continue
            elif a.is_Mul:
                if _coeff_isneg(a):
                    ops.append(NEG)
                    if a.args[0] is S.NegativeOne:
                        a = a.as_two_terms()[1]
                    else:
                        a = -a
                n, d = fraction(a)
                if n.is_Integer:
                    ops.append(DIV)
                    if n < 0:
                        ops.append(NEG)
                    args.append(d)
                    continue # won't be -Mul but could be Add
                elif d is not S.One:
                    if not d.is_Integer:
                        args.append(d)
                    ops.append(DIV)
                    args.append(n)
                    continue # could be -Mul
            elif a.is_Add:
                aargs = list(a.args)
                negs = 0
                for i, ai in enumerate(aargs):
                    if _coeff_isneg(ai):
                        negs += 1
                        args.append(-ai)
                        if i > 0:
                            ops.append(SUB)
                    else:
                        args.append(ai)
                        if i > 0:
                            ops.append(ADD)
                if negs == len(aargs): # -x - y = NEG + SUB
                    ops.append(NEG)
                elif _coeff_isneg(aargs[0]): # -x + y = SUB, but already recorded ADD
                    ops.append(SUB - ADD)
                continue
            if a.is_Pow and a.exp is S.NegativeOne:
                ops.append(DIV)
                args.append(a.base) # won't be -Mul but could be Add
                continue
            if (a.is_Mul or
                a.is_Pow or
                a.is_Function or
                isinstance(a, Derivative) or
                isinstance(a, C.Integral)):

                o = C.Symbol(a.func.__name__.upper())
                # count the args
                if (a.is_Mul or isinstance(a, C.LatticeOp)):
                    ops.append(o*(len(a.args) - 1))
                else:
                    ops.append(o)
            if not a.is_Symbol:
                args.extend(a.args)

    elif type(expr) is dict:
        ops = [count_ops(k, visual=visual) +
               count_ops(v, visual=visual) for k, v in expr.iteritems()]
    elif iterable(expr):
        ops = [count_ops(i, visual=visual) for i in expr]
    elif not isinstance(expr, Basic):
        ops = []
    else: # it's Basic not isinstance(expr, Expr):
        assert isinstance(expr, Basic)
        ops = [count_ops(a, visual=visual) for a in expr.args]

    if not ops:
        if visual:
            return S.Zero
        return 0

    ops = Add(*ops)

    if visual:
        return ops

    if ops.is_Number:
        return int(ops)

    return sum(int((a.args or [1])[0]) for a in Add.make_args(ops))

def nfloat(expr, n=15, exponent=False):
    """Make all Rationals in expr Floats except if they are exponents
    (unless the exponents flag is set to True).

    Examples
    ========

    >>> from sympy.core.function import nfloat
    >>> from sympy.abc import x, y
    >>> from sympy import cos, pi, S, sqrt
    >>> nfloat(x**4 + x/2 + cos(pi/3) + 1 + sqrt(y))
    x**4 + 0.5*x + sqrt(y) + 1.5
    >>> nfloat(x**4 + sqrt(y), exponent=True)
    x**4.0 + y**0.5

    """

    if iterable(expr, exclude=basestring):
        if isinstance(expr, (dict, Dict)):
            return type(expr)([(k, nfloat(v, n, exponent)) for k, v in
                               expr.iteritems()])
        return type(expr)([nfloat(a, n, exponent) for a in expr])
    elif not isinstance(expr, Expr):
        return float(expr)
    elif expr.is_Float:
        return expr.n(n)
    elif expr.is_Integer:
        return Float(float(expr)).n(n)
    elif expr.is_Rational:
        return Float(expr).n(n)

    if not exponent:
        pows = [p for p in expr.atoms(Pow) if p.exp.is_Rational and
                p.exp.q != 1]
        pows.sort(key=count_ops)
        pows.reverse()
        rats = {}
        for p in pows:
            if p.exp not in rats:
                e = Dummy()
                rats[p.exp] = e
        reps = [(p, Pow(p.base, rats[p.exp], evaluate=False)) for p in pows]
        rv = expr.subs(reps).n(n).subs([(v, k) for k, v in rats.iteritems()])
    else:
        expr = expr.n(n)
        pows = [p for p in expr.atoms(Pow) if p.exp.is_Integer]
        pows.sort(key=count_ops)
        pows.reverse()
        ints = {}
        for p in pows:
            if p.exp not in ints:
                ints[p.exp] = Float(float(p.exp))
        reps = [(p, p.base**ints[p.exp]) for p in pows]
        rv = expr.subs(reps)

    funcs = [f for f in rv.atoms(Function)]
    funcs.sort(key=count_ops)
    funcs.reverse()
    return rv.subs([(f, f.func(*[nfloat(a, n, exponent)
                     for a in f.args])) for f in funcs])

from sympify import sympify
from add import Add
from power import Pow
from sympy.core.symbol import Dummy
