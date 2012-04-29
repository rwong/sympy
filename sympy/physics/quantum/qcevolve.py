"""Evolution of quantum circuits.

This module provides utilities to evolve quantum circuits in SymPy.
It uses Pyevolve, a Python library for developing genetic algorithms.
More information about Pyevolve available at:

http://pyevolve.sourceforge.net/index.html

TODO or THINGS TO CONSIDER:
* Implement a mutator operator
* Implement an evaluator
* Sorting the circuits to deal with 'trivial identities'
  i.e. X(0)X(1)X(0)X(1)
  Gate sorting in gate.py limited because can't swap gates that act on
  same qubit even if they do commute.
"""

from random import Random
from sympy import Basic
from pyevolve.GenomeBase import GenomeBase
from sympy.physics.quantum.circuitutils import *

__all__ = [
    'GQCBase',
    'GQCLinear',
]

class GQCBase(Basic, GenomeBase):
    """A base representation of quantum circuits for genetic algorithms.

    Specifically, GQCBase is used for genetic programming,
    a specialization of genetic algorithms that evolve computer
    programs, or generally, algorithms.  Each quantum circuit
    represents a quantum algorithm.

    The base class provides no default behavior other than those
    provided by Basic and GenomeBase; all subclasses are expected
    to provide class specific implementations.
    """

    def __new__(cls, *args):
        # args is the quantum circuit representing a genome
        obj = Basic.__new__(cls, *args)
        return obj

    @property
    def circuit(self):
        return self.args

    def __repr__(self):
        """Return a string representation of GQCBase"""
        rep = GenomeBase.__repr__(self)
        rep += "- GQCBase\n"
        rep += "\tCircuit:\t\t %s\n\n" % (self.circuit,)
        return rep

class GQCLinear(GQCBase):
    """A linear program representation of quantum circuits.

    This class also does not provide behavior for the following:

        * Initializer operator
        * Mutator operator
        * Crossover operator
        * Evaluation function

    These functions must be set before an instance of the
    class can be used.

    GQCLinear was created to provide a meaningful name
    for a representation of quantum circuits.
    """

    def __new__(cls, *args, **kargs):
        # args is the quantum circuit representing a genome
        # kargs should a variable length dictionary
        obj = GQCBase.__new__(cls, *args)

        obj._genome_circuit = args
        obj._gate_identities = False
        obj._insert_choices = []

        # Doing this is a questionable design
        if 'GateIdentity' in kargs:
            obj._gate_identities = kargs['GateIdentity']

        if 'choices' in kargs:
            obj._insert_choices = kargs['choices']

        if obj._gate_identities:
            collapse_func = lambda acc, an_id: acc + list(an_id.symbolic_ids)
            ids_flat = reduce(collapse_func, obj._insert_choices, [])
            obj._insert_choices = ids_flat

        return obj

    @property
    def genome_circuit(self):
        return self._genome_circuit

    @genome_circuit.setter
    def genome_circuit(self, new_circuit):
        self._genome_circuit = new_circuit

    @property
    def insert_choices(self):
        # List of circuits that could be inserted into another circuit
        return self._insert_choices

    def __repr__(self):
        """Return a string representation of GQCBase"""
        rep = GQCBase.__repr__(self)
        rep += "- GQCLinear\n"
        rep += "\tIdentities:\t\t %s\n\n" % (self.identities,)
        return rep

"""
For the current problem of optimizing quantum circuits,
a semi-genetic programming approach is used where only
the mutation operation is applied to create future populations.

The first approach keeps all members of the population
within the same equivalence class of the original circuit.
"""
def linear_init(genome, **args):
    """Initialization function for optimizing quantum circuits
       problem using an linear circuit representataion.

    Parameters
    ==========
    genome : GQCLinear
        The genome in the population
    args : any (variable length)
        In many cases, will include an instance of GSimpleGA
    """

    new_circuit = random_insert(
                      genome.genome_circuit,
                      genome.insert_choices
                  )

    genome.genome_circuit = new_circuit

def linear_mutator(genome, **args):
    """Mutator function for optimizing quantum circuits
       problem using an linear circuit representataion.

    Parameters
    ==========
    genome : GQCLinear
        The genome in the population
    args : any (variable length)
        In many cases, will include an instance of GSimpleGA
    """

    # The mutator may either look for identities in
    # the circuit and make a reduction or it may
    # insert new identities into the circuit.

    # Return the number of mutations that occurred
    # with this genome (following convention)
    pass

def linear_eval(chromosome):
    """Evaluation function for optimizing quantum circuits
       problem using an linear circuit representataion."""
    pass
