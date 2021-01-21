"""
Useful functions for mechanalyzer.parser
- mechanism reading
- extract useful info from the mechanism (reactions, formulas..)
"""

import sys
import copy
import numpy as np
import automol
from mechanalyzer.parser import ckin_ as ckin


def read_mechanism_file(mech_str, mech_type, spc_dct, sort_rxns=False):
    """ Get the reactions and species from the mechanism input
    """

    # Parse the info from the chemkin file
    if mech_type == 'chemkin':
        formulas_dct, formulas, rct_names, prd_names, rxn_names = ckin.parse(
            mech_str, spc_dct, sort_rxns)
    else:
        raise NotImplementedError

    return [formulas_dct, formulas, rct_names, prd_names, rxn_names]
    # list, list of tuples, list of tuples, list


def filter_keys(dct_1, dct_2):
    '''
    Given 2 dictionaries, with 1 bigger than 2,
    it filters out from 1 all the entries present in 2
    Returns filtered dictionary
    '''

    keys_topop = list(dct_2.keys())

    for key in keys_topop:
        try:
            dct_1.pop(key, None)
        except KeyError:
            continue

    return dct_1

########################## useful functions to the sorter #######################


def order_rct_bystoich(rct_names_lst, spc_dct=None):
    '''
    reorder reactants and products based on the higher number of atoms
    If no species dictionary is given as input: reorder just according to name length,
    if length or stoichiometry is the same, by alphabetical order
    '''
    rct_names_lst_ordered = copy.deepcopy(rct_names_lst)
    ich_dct = {}
    if spc_dct:
        for key in spc_dct.keys():
            if 'ts' not in key and 'global' not in key:
                ich_dct[key] = spc_dct[key]['inchi']

        for key, val in enumerate(rct_names_lst_ordered):
            rct_names = val
            rct_ichs = list(map(ich_dct.__getitem__, rct_names))
            fml_rct = list(map(automol.inchi.formula, rct_ichs))
            atoms_rct = list(map(automol.formula.atom_count, fml_rct))
            if len(rct_names) == 2:
                if atoms_rct[1] > atoms_rct[0]:
                    # swap places of reactants 1 and 2
                    rct_names_lst_ordered[key] = (rct_names[1], rct_names[0])
                elif atoms_rct[1] == atoms_rct[0]:
                    rct_names = list(rct_names)
                    rct_names.sort()
                    rct_names_lst_ordered[key] = tuple(rct_names)

    else:
        for key, val in enumerate(rct_names_lst_ordered):
            rct_names = val
            if len(rct_names) == 2:
                if len(rct_names[1]) > len(rct_names[0]):
                    # swap places of reactants 1 and 2
                    rct_names_lst_ordered[key] = (rct_names[1], rct_names[0])
                elif len(rct_names[1]) == len(rct_names[0]):
                    rct_names = list(rct_names)
                    rct_names.sort()
                    rct_names_lst_ordered[key] = tuple(rct_names)

    return rct_names_lst_ordered


def count_atoms(fml_list):
    '''
    count C and N atoms in formula list
    should go somewhere else?
    '''
    count_C_lst = []
    count_N_lst = []
    for fml in fml_list:
        count_C = automol.formula.element_count(fml, 'C')
        count_N = automol.formula.element_count(fml, 'N')
        count_C_lst.append(count_C)
        count_N_lst.append(count_N)

    return count_C_lst, count_N_lst


def get_S1S2(SPECIES):
    '''
    extract species 1 from tuple
    '''
    S1 = []
    S2 = []
    for S in SPECIES:
        if len(S) > 1:
            # bimol species
            S1.append(S[0])
            S2.append(S[1])
        else:
            # unimol species
            S1.append(S[0])
            S2.append('')

    return S1, S2


def get_mult(spc_tuple, spc_dct):
    '''
    extracts the total multiplicity of the set of species
    spc_tuple = (A,B,C,..)
    spc_dct: species dictionary
    returns integer of the multiplicity
    '''
    mult = 1
    if isinstance(spc_tuple, str):
        spc_tuple = tuple([spc_tuple])

    for spc in spc_tuple:
        mult *= spc_dct[spc]['mult']

    return mult