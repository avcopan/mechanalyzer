"""
Functions for mechanism reading and sorting
Making script mechanalyzer/bin/mech.py more compact
"""

#import os
#import sys
#import copy
import mechanalyzer
import chemkin_io
#import pandas as pd
#import numpy as np


def readfiles(spcfile, mechfile):
    '''
    read the mechanism and the species files provided by the user
    '''
    with open(spcfile, 'r') as file_obj:
        spc_str = file_obj.read()

    # Extract species dictionary
    spc_dct = mechanalyzer.parser.spc.build_spc_dct(spc_str, 'csv')

    # Read input mechanism file
    with open(mechfile, 'r') as file_obj:
        mech_str = file_obj.read()

    # extract rxn block and build reaction parameter dictionary
    units = chemkin_io.parser.mechanism.reaction_units(mech_str)
    block_str = chemkin_io.parser.mechanism.reaction_block(mech_str)
    rxn_param_dct = chemkin_io.parser.reaction.param_dct(
        block_str, units[0], units[1])
    # extract elements
    el_block = chemkin_io.parser.mechanism.element_block(mech_str)
    elem_tuple = chemkin_io.parser.species.names(el_block)

    return spc_dct, rxn_param_dct, elem_tuple


def build_dct(spc_dct, rxn_param_dct):
    '''
    Build required info for mech sorting
    '''
    # extract info from dictionary:
    # reactants and products
    rcts, prds = zip(*rxn_param_dct.keys())
    rct_names_lst = list(rcts)
    prd_names_lst = list(prds)

    # inchis dictionary
    ich_dct = mechanalyzer.parser.ckin_.get_ich_dct(spc_dct)

    # formulas and reaction names
    formula_dct, formula_str, rxn_name = mechanalyzer.parser.ckin_.mech_info(
        rct_names_lst, prd_names_lst, ich_dct)

    mech_info = [formula_dct, formula_str,
                 rct_names_lst, prd_names_lst, rxn_name]

    return mech_info


def sort_mechanism(mech_info, spc_dct, sort_str, isolate_species):
    '''
    mech_info: formulas, reaction names
    spc_dct: species dictionary
    sort_str: list with sorting criteria
    isolate_species: list of species you want to isolate in the final mechanism

    calls sorting functions in mechanalyzer/pes
    returns the rxn indices associated with the comments about sorting
    '''
    # call the sorting class
    srt_mch = mechanalyzer.parser.sort.SortMech(mech_info, spc_dct)
    # sort according to the desired criteria
    srt_mch.sort(sort_str, isolate_species)
    # returns the sorted indices and the corresponding comments
    sorted_idx, cmts_dct, spc_dct = srt_mch.return_mech_df()

    return sorted_idx, cmts_dct, spc_dct


def reordered_mech(rxn_param_dct, sorted_idx):
    '''
    rxn_param_dct: non-sorted reactions
    sorted_idx: indices of the rxn_param_dct in the desired order
    cmts_dct: comments related to new_idx containing the rxn class
    '''
    sorted_val = list(map(rxn_param_dct.get, sorted_idx))
    rxn_param_dct_sorted = dict(zip(sorted_idx, sorted_val))

    return rxn_param_dct_sorted


def write_mech(elem_tuple, spc_dct, rxn_param_dct_sorted, sortedmech_name, comments=None):
    '''
    elem_tuple: tuple with elements
    spc_dct: species dictionary
    rxn_param_dct_sorted: reaction parameters dictionary in the desired order
    cmts_dct: comments dictionary associated with the sorted mechanism
    sortedmech_name: name of the final mech
    '''
    # reorder spc_dct before writing to make it nicer
    spc_dct = mechanalyzer.parser.spc.order_species_by_atomcount(spc_dct)
    # write
    chemkin_io.writer.mechanism.write_chemkin_file(
        elem_tuple=elem_tuple, spc_dct=spc_dct, rxn_param_dct=rxn_param_dct_sorted,
        filename=sortedmech_name, comments=comments)


