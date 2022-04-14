"""
  Code to expand the mechanism using stereochemistry

    maybe remove all inchis that are not incomplete?
"""
import os
import itertools as it

import automol
from chemkin_io.writer._util import format_rxn_name
from autorun import execute_function_in_parallel
import mechanalyzer.parser
from mechanalyzer.builder._update import update_spc_dct_from_reactions
from mechanalyzer.builder._update import update_rxn_dct
from mechanalyzer.builder._names import rxn_name_str
from chemkin_io.writer._util import format_rxn_name


# MAIN CALLABLE
# def expand_mech_stereo(mech_rxn_dct, mech_spc_dct, nprocs='auto'):
def expand_mech_stereo(inp_mech_rxn_dct, inp_mech_spc_dct,
                       remove_enantiomer_rxns=True, nprocs='auto'):
    """ Build list of stereochemistry to reactions

        Currently, we assume that the species in them mech_spc_dct have
        stereochemistry already added to them.
    """

    def _expand(name_ich_dct, rxns, output_queue):
        """ Expand reactons
        """
        # First loop over all reactions to add stereo
        all_ste_rxns = []
        for rxn in rxns:

            log1 = f'\nExpanding Stereo for Reaction: {format_rxn_name(rxn)}\n'
            print(log1)

            # Reformat reaction to use InChI instead of mechanism name
            # Split thrdbdy off, not needed for stereo code, add back later
            rxn_ich = _rxn_name_to_ich(rxn, name_ich_dct)
            _rxn_ich = (rxn_ich[0], rxn_ich[1])
            thrdbdy = rxn_ich[2]

            # Build list of all stereochemically allowed versions of reaction
            ste_rxns_lst, log2 = _ste_rxn_lsts(_rxn_ich)
            print(log2)
            # Appropriately format the reactions with third body
            ste_rxns_lst = _add_third(ste_rxns_lst, thrdbdy)
            all_ste_rxns.append(ste_rxns_lst)
        output_queue.put(tuple(all_ste_rxns))
        print(f'Processor {os.getpid()} finished')

    # Dictionaries to map name to inchi
    name_ich_dct = mechanalyzer.parser.spc.name_inchi_dct(inp_mech_spc_dct)

    # Generate all stereo reactons from the initial set
    rxns = tuple(inp_mech_rxn_dct.keys())
    args = (name_ich_dct,)
    pes_noste_rxns_dct = _rxns_noste_pes_dct(rxns, name_ich_dct)
    all_ste_rxns = ()

    # Loop over the PES (stoich similar)
    forms = list(pes_noste_rxns_dct.keys())
    # ste_rxn_cnt = 0
    full_ste_rxn_lst = []
    full_ste_spc_lst = []
    for formula in forms:
        noste_rxns_dct = pes_noste_rxns_dct[formula]
        print('PES: {} has {:g} reactions'.format(
            formula, len(noste_rxns_dct.keys())))
        pes_gra, ccs_dct = _pes_gra(noste_rxns_dct)
        # Loop over ccs (connected channels)
        for ccs_idx, rxns in ccs_dct.items():
            args = (name_ich_dct,)
            ste_rxns = [
                key for key, val in noste_rxns_dct.items() if val in rxns]
            # expand each reaction to all valid stoich versions
            ste_rxns = execute_function_in_parallel(
                _expand, ste_rxns, args, nprocs=nprocs)
            ste_rxn_dct = _make_ste_rxn_dct(ste_rxns)
            ccs_rxn_gra = _make_ccs_rxn_gra(
                ste_rxn_dct, pes_gra)

            # Count all of the stereo reactions
            # Build list of stereo species
            for _rxn_lst in ste_rxns:
                # ste_rxn_cnt += len(_rxn_lst)
                for _rxnx in _rxn_lst:
                    for rct in _rxnx[0]:
                        if rct not in full_ste_spc_lst:
                            full_ste_spc_lst.append(rct)
                    for prd in _rxnx[1]:
                        if prd not in full_ste_spc_lst:
                            full_ste_spc_lst.append(prd)
                    full_ste_rxn_lst.append(_rxnx)

            # split into ccs to sccs
            sccs_rxn_gra = _split_ste_ccs(ccs_rxn_gra)
            all_ste_rxns += (sccs_rxn_gra,)

    print('Number of reactions in the full expansion:', len(full_ste_rxn_lst))
    print('Number of species in the full expansion:', len(full_ste_spc_lst))
    for x in full_ste_rxn_lst:
        print(x)
    print('-----')
    print('-----')
    print('-----')
    print('-----')

    return all_ste_rxns


def valid_enantiomerically(ste_mech_spc_dct):
    """ are there NOT enantiomeric species in this reaction list
    """
    rule_out = False
    for spc_name_i, spc_name_j in list(
            it.combinations(ste_mech_spc_dct.keys(), 2)):
        no_ste_ich_i = automol.chi.standard_form(
            ste_mech_spc_dct[spc_name_i]['inchi'], stereo=False)
        no_ste_ich_j = automol.chi.standard_form(
            ste_mech_spc_dct[spc_name_j]['inchi'], stereo=False)
        if no_ste_ich_i == no_ste_ich_j:
            if automol.chi.are_enantiomers(
                    ste_mech_spc_dct[spc_name_i]['inchi'],
                    ste_mech_spc_dct[spc_name_j]['inchi']):
                print(
                    'ruling out because',
                    ste_mech_spc_dct[spc_name_i]['inchi'],
                    ste_mech_spc_dct[spc_name_j]['inchi'])
                rule_out = True
                break
    return rule_out is False


def _make_ste_rxn_dct(ste_rxns):
    """  A dictionary with a stereoless reaction ichs as the
         key and stereo expansions ich reaction list as value
    """
    ste_rxn_dct = {}
    for rxn_lst in ste_rxns:
        ichs1, ichs2, _ = rxn_lst[0]
        noste_rxn, _, _ = _noste_rxn((ichs1, ichs2))
        ste_rxn_dct[noste_rxn] = rxn_lst
    return ste_rxn_dct


def _make_ccs_rxn_gra(ste_rxn_dct, pes_gra):
    """ merges the pes_gra and the reaction list
    """
    print('pes_gra test')
    for x in pes_gra:
        print(x)
    print('-----')
    ccs_rxn_gra = {}
    for noste_rxn, ste_exp_lst in ste_rxn_dct.items():
        print('noste_rxn', noste_rxn)
        ccs_rxn_gra[noste_rxn] = (
            pes_gra[noste_rxn],
            ste_exp_lst)
    return ccs_rxn_gra


def _is_ste_conn(rxn, rxn_lst):
    """ Are to rxns connected stereochemically?
    """
    all_pes_ichs = []
    ichsi, ichsj, _ = rxn
    i_is_conn = False
    j_is_conn = False
    for ichs1, ichs2, _ in rxn_lst:
        all_pes_ichs.append(ichs1)
        all_pes_ichs.append(ichs2)
    if ichsi in all_pes_ichs:
        i_is_conn = True
    if ichsj in all_pes_ichs:
        j_is_conn = True
    return i_is_conn or j_is_conn


def _enant_rxn(rxn_i):
    """ Returns the enantiomer of a reaction, 
        uses None if there is no enantiomer
    """
    check_ent = [
        tuple(map(automol.chi.reflect, ichs)) for ichs in rxn_i[:-1]]
    if check_ent[0] == rxn_i[0]:
        check_ent[0] = None
    if check_ent[1] == rxn_i[1]:
        check_ent[1] = None
    check_ent.append(rxn_i[-1])
    return check_ent


def _split_ste_ccs(ccs_rxn_gra):
    """ seperates a ccs into a dictionary of sccs
        where a numeric index is a key and a
        list of stereo-reactions (in ichs) is val
    """
    def _recursive_step(
            noste_rxn, ccs_rxn_gra, sccs_rxn_gra,
            considered_rxns):
        adj_noste_rxn_lst, exp_rxns_lst = ccs_rxn_gra[noste_rxn]
        considered_rxns.append(noste_rxn)
        orig_sccs_rxn_gra = sccs_rxn_gra.copy()

        # Loop through reaction's expansions and put them
        # in appropriate sccs graph
        for rxn_i in exp_rxns_lst:
            is_new_stereo = True
            enant_idx_lst = []

            # Loop over propogating sccs graphs
            for idx in sccs_rxn_gra:

                # check if this stereo-rxn is connected to the sccs
                if _is_ste_conn(rxn_i, sccs_rxn_gra[idx]):
                    check_ent = _enant_rxn(rxn_i)

                    # check if this rxns enantiomers are also in the sccs
                    if _is_ste_conn(check_ent, sccs_rxn_gra[idx]):
                        if idx < len(orig_sccs_rxn_gra):
                            enant_idx_lst.append(idx)
                        continue
                    sccs_rxn_gra[idx] += (rxn_i,)
                    is_new_stereo = False
            if is_new_stereo:
                # if it was both ste-connected and had ents-connected
                # copy the sccs up to the point that enantiomers got in there
                # and add this reaction to it
                if enant_idx_lst:
                    for enant_idx in enant_idx_lst:
                        sccs_rxn_gra[len(sccs_rxn_gra)] = orig_sccs_rxn_gra[
                            enant_idx]
                        sccs_rxn_gra[len(sccs_rxn_gra) - 1] += (rxn_i,)
                else:
                    # if it was just totally independent, create a new sccs
                    sccs_rxn_gra[len(sccs_rxn_gra)] = (rxn_i,)

        # walk through adjacent reactions and repeat the procedure recursively
        # until all reactions are considered
        for noste_rxn_i in adj_noste_rxn_lst:
            if noste_rxn_i not in considered_rxns:
                sccs_rxn_gra, considered_rxns = _recursive_step(
                    noste_rxn_i, ccs_rxn_gra, sccs_rxn_gra,
                    considered_rxns)
        return sccs_rxn_gra, considered_rxns

    # initialize
    sccs_rxn_gra = {}
    considered_rxns = []

    # pass through first reaction in a ccs
    start_key = list(ccs_rxn_gra.keys())[0]
    adj_noste_rxn_lst, exp_rxns_lst = ccs_rxn_gra[start_key]
    start_rxn = exp_rxns_lst[0]
    considered_rxns.append(start_rxn)
    sccs_rxn_gra[0] = (start_rxn,)
    orig_sccs_rxn_gra = {0: ()}

    # Loop through reaction's expansions and put them
    # in appropriate sccs graph
    for rxn_i in exp_rxns_lst[1:]:
        is_new_stereo = True
        enant_idx_lst = []

        # Loop over propogating sccs graphs
        for idx in sccs_rxn_gra:

            # check if this stereo-rxn is connected to the sccs
            if _is_ste_conn(rxn_i, sccs_rxn_gra[idx]):
                check_ent = _enant_rxn(rxn_i)

                # check if this rxns enantiomers are also in the sccs
                if _is_ste_conn(check_ent, sccs_rxn_gra[idx]):
                    if idx < len(orig_sccs_rxn_gra):
                        enant_idx_lst.append(idx)
                    continue
                sccs_rxn_gra[idx] += (rxn_i,)
                is_new_stereo = False
        if is_new_stereo:
            # if it was both ste-connected and had ents-connected
            # copy the sccs up to the point that enantiomers got in there
            # and add this reaction to it
            if enant_idx_lst:
                for enant_idx in enant_idx_lst:
                    sccs_rxn_gra[len(sccs_rxn_gra)] = orig_sccs_rxn_gra[
                        enant_idx]
                    sccs_rxn_gra[len(sccs_rxn_gra) - 1] += (rxn_i,)
            else:
                # if it was just totally independent, create a new sccs
                sccs_rxn_gra[len(sccs_rxn_gra)] = (rxn_i,)

    # walk through adjacent reactions and repeat the procedure recursively
    # until all reactions are considered
    for noste_rxn_i in adj_noste_rxn_lst:
        if noste_rxn_i not in considered_rxns:
            sccs_rxn_gra, considered_rxns = _recursive_step(
                noste_rxn_i, ccs_rxn_gra, sccs_rxn_gra, considered_rxns)
    return sccs_rxn_gra


def _pes_gra(noste_rxn_dct):
    """ seperates a list of reactions into graphs
        pes_gra: graph of a reaction (key) 
            and a list (value) the reactions with theh same stoichiometry
        ccs_gra: graph of reaction (key
            and list (value) of reactions that are connected through wells
    """
    def _recursive_add(rxna, pes_gra, sub_pes_gra_i):
        for rxnb in pes_gra[rxna]:
            if rxnb in sub_pes_gra_i:
                continue
            sub_pes_gra_i += (rxnb,)
            sub_pes_gra_i = _recursive_add(rxnb, pes_gra, sub_pes_gra_i)
        return sub_pes_gra_i

    # initialize
    pes_gra = {}
    ccs_gra = {}
    idx = 0

    # loop over reactions
    for rxna in noste_rxn_dct:
        ichsi, ichsj = noste_rxn_dct[rxna]
        for rxnb in noste_rxn_dct:
            if rxna == rxnb:
                continue
            noste_rxnb = noste_rxn_dct[rxnb]
            if (
                    (len(ichsi) == 1 and ichsi in noste_rxnb) or
                    (len(ichsj) == 1 and ichsj in noste_rxnb)):
                if (ichsi, ichsj) not in pes_gra:
                    pes_gra[(ichsi, ichsj)] = (noste_rxnb,)
                else:
                    pes_gra[(ichsi, ichsj)] += (noste_rxnb,)
        if (ichsi, ichsj) not in pes_gra:
            print(rxna, ' IS DISCONNECTED')
            pes_gra[(ichsi, ichsj)] = ()

    # loops over PESes
    for rxna in pes_gra:
        if idx not in ccs_gra:
            ccs_gra[idx] = (rxna,)
        elif not any(
                rxna in ccs_gra[idx_j] for idx_j in ccs_gra):
            idx += 1
            ccs_gra[idx] = (rxna,)
        else:
            continue
        ccs_gra[idx] = _recursive_add(rxna, pes_gra, ccs_gra[idx])

    for idx in ccs_gra:
        print('CCS {:g}: {:g} reactions'.format(idx, len(ccs_gra[idx])))

    return pes_gra, ccs_gra


def _noste_rxn(rxn_ichs):
    ichs1, ichs2 = rxn_ichs
    noste_ichs1 = ()
    noste_ichs2 = ()
    form1 = ()
    form2 = ()
    for ich in ichs1:
        noste_ichs1 += (automol.chi.standard_form(ich, stereo=False),)
        form1 += (automol.chi.formula(ich),)
    for ich in ichs2:
        noste_ichs2 += (automol.chi.standard_form(ich, stereo=False),)
        form2 += (automol.chi.formula(ich),)
    form1 = automol.formula.join(*form1) if len(form1) > 1 else form1[0]
    form2 = automol.formula.join(*form2) if len(form2) > 1 else form2[0]
    noste_rxn = (automol.inchi.sorted_(noste_ichs1), automol.inchi.sorted_(noste_ichs2))
    return noste_rxn, form1, form2


def _rxns_noste_pes_dct(rxns, name_ich_dct):
    """Dictionary of dictionaries for FORMULA: {origanalRXN: RXnwithoutstereo}
    """
    noste_dct = {}
    for rxn in rxns:
        ichs1, ichs2, _ = _rxn_name_to_ich(rxn, name_ich_dct)
        noste_rxn, form1, form2 = _noste_rxn((ichs1, ichs2,))
        if not automol.formula.string(form1) in noste_dct:
            noste_dct[automol.formula.string(form1)] = {rxn: noste_rxn}
        else:
            noste_dct[automol.formula.string(form1)][rxn] = noste_rxn
    return noste_dct


def _sort_expansion(all_ste_rxns):
    rxn_ich_count = {}
    for rxn_lst in all_ste_rxns:
        for rxn in rxn_lst:
            ichs1, ichs2, _ = rxn
            for ich in ichs1 + ichs2:
                ich_no_ste = automol.chi.standard_form(ich, stereo=False)
                if ich_no_ste not in rxn_ich_count:
                    rxn_ich_count[ich_no_ste] = 1
                elif ich_no_ste != ich:
                    rxn_ich_count[ich_no_ste] += 1
    sort_val_lst = []
    for rxn_lst in all_ste_rxns:
        sort_val = 0
        for rxn in rxn_lst:
            ichs1, ichs2, _ = rxn
            for ich in ichs1 + ichs2:
                ich_no_ste = automol.chi.standard_form(ich, stereo=False)
                sort_val += rxn_ich_count[ich_no_ste]
        sort_val_lst.append(sort_val)

    return [x for _, x in sorted(zip(sort_val_lst, all_ste_rxns), reverse=True)]


def remove_stereochemistry(inp_mech_rxn_dct, inp_mech_spc_dct):
    """ Generate a mechanism with all stereochemistry removed
    """

    print('Removing stereochemistry from the species and reactions')

    # Loop over the reactions and generate the variants without stereo
    name_ich_dct = mechanalyzer.parser.spc.name_inchi_dct(inp_mech_spc_dct)

    noste_rxns = ()
    for rxn in inp_mech_rxn_dct:

        # Write rxn in terms of inchi, then remove the inchi strings
        rxn_ich = _rxn_name_to_ich(rxn, name_ich_dct)
        rxn_ich_noste = _remove_rxn_stereo(rxn_ich)

        if rxn_ich_noste not in noste_rxns:
            noste_rxns += (rxn_ich_noste,)

    # Update the mechanism objects with unique spc and rxns
    noste_spc_dct, noste_rxn_dct = {}, {}
    noste_spc_dct = update_spc_dct_from_reactions(noste_rxns, noste_spc_dct)
    noste_rxn_dct = update_rxn_dct(noste_rxns, noste_rxn_dct, noste_spc_dct)

    return noste_rxn_dct, noste_spc_dct


# Build reaction lists
def _ste_rxn_lsts(rxn_ich):
    """ Build reaction onjects
    """
    # Build reaction objects
    rxn_obj_sets = automol.reac.util.rxn_objs_from_inchi(
        rxn_ich[0], rxn_ich[1])
    try:
        rxn_obj = rxn_obj_sets[0][0]  # expand just with rxn object
    except TypeError:
        print('No ID', rxn_ich)

    # Build a list of stereo reactions
    ste_rxn_ichs = ()
    for ste_rxn in automol.reac.expand_stereo(rxn_obj):
        rct_gras = automol.reac.reactant_graphs(ste_rxn)
        prd_gras = automol.reac.product_graphs(ste_rxn)
        attempt = 1
        while attempt < 4:
            try:
                rct_ichs, prd_ichs = (), ()
                for gra in rct_gras:
                    rct_ichs += (automol.graph.chi(gra, stereo=True),)
                for gra in prd_gras:
                    prd_ichs += (automol.graph.chi(gra, stereo=True),)
                ste_rxn_ichs += ((rct_ichs, prd_ichs),)
                break
            except:
                attempt += 1

            if attempt == 3:
                print('Fail to get stereo in 3 attempts', rxn_ich)

    # Set log message
    log = f' - Reaction identified as {rxn_obj.class_}.\n'

    return ste_rxn_ichs, log


# Functions to check and sort the reactions by stereochemistry
def _remove_enantiomer_reactions(ste_rxn_lst, reacs_stereo_inchi=None):
    """ Take all reactions that occur from stereochemically
        and determine which reactions should be kept and
        whihc are unneccessary

        There are two reduction methods to reduce the set.
        If the reactant inchi is given, we grab reactions that use that
        stereo. Otherwise, we use internal logic in autochem to enfore
        m0 stereochemistry in the InChI strings.
    """

    # Convert reactants stero inchi to set for comparisons
    reacs_stereo_inchi = set(reacs_stereo_inchi)

    # Remove redundant sets and rebuild proper list
    if reacs_stereo_inchi is not None:
        log = ' - Reducing reactions to those with reactant stereochemistry\n'
        # Checks the InChI of the reactants in each reaction to see if they
        # match the input stereo inchi
        f_ste_rxn_lst = tuple(rxn for rxn in ste_rxn_lst
                              if set(rxn[0]) == reacs_stereo_inchi)
    else:
        log = ' - Reducing reactions to enforce InChI/m0 stereo throughout\n'
        f_ste_rxn_lst = automol.chi.filter_enantiomer_reactions(ste_rxn_lst)

    # Print the removed reactions
    removed_ste_rxn_lst = set(ste_rxn_lst) - set(f_ste_rxn_lst)

    return f_ste_rxn_lst, removed_ste_rxn_lst, log


# Formatters and printers
def _stereo_results(rxn, f_ste_rxns_lst, removed_ste_rxns_lst):
    """ Print the final filtered reactions and those removed
    """

    # Print final list of reactions
    log = f' - Stereochemical Versions of Reaction: {rxn_name_str(rxn)}\n'
    for ste_rxn in f_ste_rxns_lst:
        log += '    ' + rxn_name_str(ste_rxn, newline=True) + '\n'

    # Print removed reactions
    if removed_ste_rxns_lst:
        log += (' - Redundant, enantiomeric reactions '
                'precluded from final list\n')
        for ste_rxn in removed_ste_rxns_lst:
            log += '    ' + rxn_name_str(ste_rxn, newline=True) + '\n'

    return log


def _add_third(rxn_lst, thrdbdy):
    """ Format a rxn list to have the third-body added back
    """
    return tuple((rxn[0], rxn[1], thrdbdy) for rxn in rxn_lst)


def _rxn_name_to_ich(rxn, ich_dct):
    """ Convert a reacion written with spc names to spc inchis
        Third body list remains the same
    """

    # Convert reactant and product names to InChIs
    _rxn = (
        tuple(ich_dct.get(rgt) for rgt in rxn[0]),
        tuple(ich_dct.get(rgt) for rgt in rxn[1]),
        rxn[2]
    )

    # Set rxn_ich to None
    if (
        any(rgt is None for rgt in _rxn[0]) or
        any(rgt is None for rgt in _rxn[1])
    ):
        _rxn = None

    return _rxn


def _remove_rxn_stereo(rxn):
    """ Generate rxn in inchi representation with no stereo
    """

    return (
        tuple(automol.chi.standard_form(ich, stereo=False) for ich in rxn[0]),
        tuple(automol.chi.standard_form(ich, stereo=False) for ich in rxn[1]),
        rxn[2]
    )


def _rxn_smiles(rxn):
    """ write a reaction into smles
    """
    return (
        tuple(automol.chi.smiles(rgt) for rgt in rxn[0]),
        tuple(automol.chi.smiles(rgt) for rgt in rxn[1]),
    )
