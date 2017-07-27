# -*- coding: utf-8 -*-
"""
Initial version based on 
https://github.com/iiasa/ceds_harmonization_analysis by Matt Gidden
"""

import os
import warnings

import re
import numpy as np
import pandas as pd
import seaborn as sns

# ignore warnings
warnings.filterwarnings('ignore')

# disable autoscroll in Jupyter notebooks
try:
    get_ipython().run_cell_magic(u'javascript', u'',
                                 u'IPython.OutputArea.prototype._should_scroll = function(lines) { return false; }')
except:
    pass

all_idx_cols = ['model', 'scenario', 'region', 'variable', 'year', 'unit']
iamc_idx_cols = ['model', 'scenario', 'region', 'variable', 'unit']

# %% class for working with IAMC-style timeseries data


class IamDataFrame(object):
    """This class is a wrapper for dataframes
    following the IAMC data convention."""

    def __init__(self, mp=None, path=None, file=None, ext='csv',
                 regions=None):
        """Initialize an instance of an IamDataFrame

        Parameters
        ----------
        mp: ixPlatform
            an instance of an ix modeling platform (ixmp)
            (if initializing from an ix platform)
        path: str
            the folder path where the data file is located
            (if reading in data from a snapshot csv or xlsx file)
        file: str
            the folder path where the data file is located
            (if reading in data from a snapshot csv or xlsx file)
        ext: str
            snapshot file extension
            (if reading in data from a snapshot csv or xlsx file)
        regions: list
            list of regions to be imported
        """
        if mp:
            raise SystemError('connection to ix platform not yet supported')
        elif file and ext:
            self.data = read_data(path, file, ext, regions)

        # define a dataframe for categorization and other meta-data
        self.cat = self.data[['model', 'scenario']].drop_duplicates()\
            .set_index(['model', 'scenario'])
        self.cat['category'] = np.nan

    def models(self, filters={}):
        """Get a list of models filtered by certain characteristics

        Parameters
        ----------
        filters: dict, optional
            filter by model, scenario, region, variable, or year
            see function select() for details
        """
        return list(self.select(filters, ['model']).model)

    def scenarios(self, filters={}):
        """Get a list of scenarios filtered by certain characteristics

        Parameters
        ----------
        filters: dict, optional
            filter by model, scenario, region, variable, or year
            see function select() for details
        """
        return list(self.select(filters, ['scenario']).scenario)

    def variables(self, filters={}):
        """Get a list of variables filtered by certain characteristics

        Parameters
        ----------
        filters: dict, optional
            filter by model, scenario, region, variable, or year
            see function select() for details
        """
        return list(self.select(filters, ['variable']).variable)

    def pivot_table(self, index, columns, filters={}, aggregated=None,
                    function='count', style='highlight_not_max'):
        """Returns a pivot table

        Parameters
        ----------
        index: str or list of strings
            rows for Pivot table
        columns: str or list of strings
            columns for Pivot table
        filters: dict, optional
            filter by model, scenario, region, variable, or year
            see function select() for details
        aggregated: str, optional
            dataframe column which should be aggregated or counted
        function: str
            function for aggregation: count, mean, sum
        """
        if not aggregated:
            return pivot_has_elements(self.select(filters, index+columns),
                                      index=index, columns=columns)
        else:
            cols = index + columns + [aggregated]
            df = self.select(filters, cols)
            if function == 'count':
                df = df.groupby(index+columns, as_index=False).count()
            elif function == 'mean':
                df = df.groupby(index+columns, as_index=False).mean().round(2)
            elif function == 'sum':
                df = df.groupby(index+columns, as_index=False).sum()

            df_pivot = df.pivot_table(values=aggregated, index=index,
                                      columns=columns, fill_value=0)
            if style == 'highlight_not_max':
                return df_pivot.style.apply(highlight_not_max)
            if style == 'heat_map':
                cm = sns.light_palette("green", as_cmap=True)
                return df_pivot.style.background_gradient(cmap=cm)
            else:
                return df_pivot

    def timeseries(self, filters={}):
        """Returns a dataframe in the standard IAMC format

        Parameters
        ----------
        filters: dict, optional
            filter by model, scenario, region, variable, or year
            see function select() for details
        """
        return self.select(filters).pivot_table(index=iamc_idx_cols,
                                                columns='year')['value']

    def validate(self, criteria, filters={}, exclude=False):
        """Run validation checks on timeseries data

        Parameters
        ----------
        criteria: dict
            dictionary of variables mapped to a dictionary of checks
            ('up' and 'lo' for respective bounds, 'year' for years - optional)
        filters: dict, optional
            filter by model, scenario & region
            (variables & years are replaced by the other arguments)
            see function select() for details
        exclude: bool
            models/scenarios failing the validation to be excluded from data
        """
        df = pd.DataFrame()
        for var, check in criteria.items():
            df = df.append(self.check(var, check,
                                      filters, ret_true=False))
        if len(df):
            df.set_index(all_idx_cols, inplace=True)
            if exclude:
                raise SystemError(
                        'excluding model/scenarios not yet supported!')

            print("These model/scenarios do not satisfy the criteria:")
            cm = sns.light_palette("green", as_cmap=True)
            return df.style.background_gradient(cmap=cm)
        else:
            print("All models and scenarios satisfy the criteria")

    def category(self, name, criteria=None, filters=None, comment=None,
                 assign=True, display=list):
        """Assign scenarios to a category according to specific criteria

        Parameters
        ----------
        name: str
            category name
        criteria: dict
            dictionary with variables mapped to applicable checks
            ('up' and 'lo' for respective bounds, 'year' for years - optional)
        filters: dict, optional
            filter by model, scenario & region
            (variables & years are replaced by args in criteria)
            see function select() for details
        comment: str
            a comment pertaining to the category
        assign: boolean (default True)
            assign categorization to data (if false, display only)
        display: str or None (default None)
            display style of scenarios assigned to this category (list, pivot)
            (no display if None)
        """
        if name and not criteria:
            df = pd.DataFrame(index=self.cat[self.cat.category == name].index)
            if display == 'list':
                return df
            elif display == 'pivot':
                return pivot_has_elements(df, 'model', 'scenario')

        else:
            cat = self.cat.index.copy()
            for var, check in criteria.items():
                cat = cat.intersection(self.check(var, check,
                                                  filters).index)

            df = pd.DataFrame(index=cat)
            if len(df):
                # assign selected model/scenario to internal category mapping
                if assign:
                    self.cat.loc[cat, 'category'] = name

                # return the model/scenario as dataframe for visual output
                if display:
                    print("The following scenarios are categorized as '" +
                          name + "':")
                    if display == 'list':
                        return df
                    elif display == 'pivot':
                        return pivot_has_elements(df, 'model', 'scenario')
            else:
                print("No scenario satisfies the criteria")

    def check(self, variable, check, filters=None, ret_true=True):
        """Check which model/scenarios satisfy specific criteria

        Parameters
        ----------
        variable: str
            variable to be checked
        check: dict
            dictionary with checks
            ('up' and 'lo' for respective bounds, 'year' for years - optional)
        filters: dict, optional
            filter by model, scenario & region
            (variables & years are replaced by arguments of 'check')
            see function select() for details
        ret_true: bool
            if true, return models/scenarios passing the check;
            otherwise, return datatframe of all failed checks
        """
        if not filters:
            filters = {}
        if 'year' in check:
            filters['year'] = check['year']
        filters['variable'] = variable
        df = self.select(filters)

        is_true = np.array([True] * len(df.value))

        for check_type, val in check.items():
            if check_type == 'up':
                is_true = is_true & (df.value <= val)

            if check_type == 'lo':
                is_true = is_true & (df.value > val)

        if ret_true:
            # if assessing a criteria for one year only
            if ('year' in check) and isinstance(check['year'], int):
                return df.loc[is_true, ['model', 'scenario', 'year']]\
                              .drop_duplicates()\
                              .set_index(['model', 'scenario'])
            # if more than one year is filtered for, ensure that
            # the criteria are satisfied in every year
            else:
                num_yr = len(df.year.drop_duplicates())
                df_agg = df.loc[is_true, ['model', 'scenario', 'year']]\
                    .groupby(['model', 'scenario']).count()
                return pd.DataFrame(index=df_agg[df_agg.year == num_yr].index)
        else:
            return df[~is_true]

    def select(self, filters={}, cols=None, idx_cols=None):
        """Select a subset of the data (filter) and set an index

        Parameters
        ----------
        filters: dict, optional
            The following columns are available for filtering:
             - 'model', 'scenario', 'region': takes a string or list of strings
             - 'variable': takes a string or list of strings,
                where ``*`` can be used as a wildcard
             - 'year': takes an integer, a list of integers or a range
                (note that the last year of a range is not included,
                so ``range(2010,2015)`` is interpreted
                as ``[2010, 2011, 2012, 2013, 2014]``)
        cols: string or list
            Columns returned for the dataframe, duplicates are dropped
        idx_cols: string or list
            Columns that are set as index of the returned dataframe
        """

        # filter by columns and list of values
        keep = np.array([True] * len(self.data))

        for col, values in filters.items():
            if col in ['model', 'scenario', 'region']:
                keep_col = keep_col_match(self.data[col], values)

            elif col == 'variable':
                keep_col = keep_col_match(self.data[col], values, True)

            elif col in ['year']:
                keep_col = keep_col_yr(self.data[col], values)

            else:
                raise SystemError(
                        'filter by column ' + col + ' not supported')
            keep = keep & keep_col

        df = self.data[keep].copy()

        # select columns (and index columns), drop duplicates
        if cols:
            if idx_cols:
                cols = cols + idx_cols
            df = df[cols].drop_duplicates()

        # set (or reset) index
        if idx_cols:
            return df.set_index(idx_cols)
        else:
            return df.reset_index(drop=True)

# %% auxiliary function for reading data from snapshot file


def read_data(path=None, file=None, ext='csv', regions=None):
    """Read data from a snapshot file in the IAMC format

    Parameters
    ----------
    path: str
        the folder path where the data file is located
    file: str
        the folder path where the data file is located
    ext: str
        snapshot file extension
    regions: list
        list of regions to be loaded from the database snapshot
    """
    if path:
        fname = '{}/{}.{}'.format(path, file, ext)
    else:
        fname = '{}.{}'.format(file, ext)

    if not os.path.exists(fname):
        raise SystemError("no snapshot file '" + fname + "' found!")

    # read from database snapshot csv
    if ext == 'csv':
        df = pd.read_csv(fname)
        df = (df.rename(columns={c: str(c).lower() for c in df.columns}))

        # filter by selected regions
        if regions:
            df = df[df['region'].isin(regions)]

        # transpose dataframe by year column
        idx = iamc_idx_cols
        numcols = sorted(set(df.columns) - set(idx))
        df = pd.melt(df, id_vars=idx, var_name='year',
                     value_vars=numcols, value_name='value')
        df.year = pd.to_numeric(df.year)

        # drop NaN's
        df.dropna(inplace=True)
    else:
        raise SystemError('file type ' + ext + ' is not supported')

    return df

# %% auxiliary functions for data filtering


def keep_col_match(col, strings, pseudo_regex=False):
    """
    matching of model/scenario names and variables to pseudo-regex (optional)
    for data filtering
    """
    keep_col = np.array([False] * len(col))

    if isinstance(strings, str):
        strings = [strings]

    for s in strings:
        if pseudo_regex:
            s = s.replace('|', '\\|').replace('*', '.*') + "$"
        pattern = re.compile(s)
        subset = filter(pattern.match, col)
        keep_col = keep_col | col.isin(subset)

    return keep_col


def keep_col_yr(col, yrs):
    """
    matching of year columns for data filtering
    """

    if isinstance(yrs, int):
        return col == yrs

    elif isinstance(yrs, list) or isinstance(yrs, range):
        return col.isin(yrs)

    else:
        raise SystemError('filtering for years by ' + yrs + ' not supported,' +
                          'must be int, list or range')

# %% auxiliary functions for table and graph formatting


def pivot_has_elements(df, index, columns):
    """
    returns a pivot table with existing index-columns combinations highlighted
    """
    df.reset_index(inplace=True)
    df['has_elements'] = (np.array([True] * len(df)))
    df_pivot = df.pivot_table(values='has_elements',
                              index=index, columns=columns, fill_value='')
    return df_pivot.style.applymap(highlight_has_element)


def highlight_has_element(val):
    """
    highlights table cells green if value is True
    """
    color = 'green' if val else 'white'
    return 'color: {0}; background-color: {0}'.format(color)


def highlight_not_max(s):
    '''
    highlight the maximum in a Series yellow.
    '''
    is_max = s == s.max()
    return ['' if v else 'background-color: yellow' for v in is_max]
