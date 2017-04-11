#!/usr/bin/python
# -*- coding: latin-1 -*-
"""
A module for classes and functions used across all ExoCTK subpackages
"""
from glob import glob
from astropy.io import fits
from astropy.utils.exceptions import AstropyWarning
from scipy.interpolate import splmake, spleval
from scipy.interpolate import RegularGridInterpolator
from functools import partial
import multiprocessing
import bibtexparser as bt
import astropy.table as at
import astropy.io.votable as vo
import matplotlib.pyplot as plt
import pkg_resources
import warnings
import numpy as np
import urllib
import os
import time

warnings.simplefilter('ignore', category=AstropyWarning)

class Filter(object):
    """
    Creates a Filter object to store a photometric filter profile
    and metadata
    
    Attributes
    ----------
    path: str
        The absolute filepath for the bandpass data, an ASCII file with
        a wavelength column in Angstroms and a response column of values 
        ranging from 0 to 1
    refs: list, str
        The references for the bandpass data
    rsr: np.ndarray
        The wavelength and relative spectral response (RSR) arrays
    Band: str
        The band name
    CalibrationReference: str
        The paper detailing the calibration
    FWHM:float
        The FWHM for the filter
    Facility: str
        The telescope facility
    FilterProfileService: str
        The SVO source
    MagSys: str
        The magnitude system
    PhotCalID: str
        The calibration standard
    PhotSystem: str
        The photometric system
    ProfileReference: str
        The SVO reference
    WavelengthCen: float
        The center wavelength
    WavelengthEff: float
        The effective wavelength
    WavelengthMax: float
        The maximum wavelength
    WavelengthMean: float
        The mean wavelength
    WavelengthMin: float
        The minimum wavelength
    WavelengthPeak: float
        The peak wavelength
    WavelengthPhot: float
        The photon distribution based effective wavelength
    WavelengthPivot: float
        The wavelength pivot
    WavelengthUCD: str
        The SVO wavelength unit
    WavelengthUnit: str
        The wavelength unit
    WidthEff: float
        The effective width
    ZeroPoint: float
        The value of the zero point flux
    ZeroPointType: str
        The system of the zero point
    ZeroPointUnit: str
        The units of the zero point
    filterID: str
        The SVO filter ID
    
    """
    def __init__(self, band, filter_directory=''):
        """
        Loads the bandpass data into the Filter object
        
        Parameters
        ----------
        band: str
            The bandpass filename (e.g. 2MASS.J)
        filter_directory: str
            The directory containing the filter files
            
        """
        # Get list of filters
        filters = filter_list(filter_directory) if filter_directory else filter_list()
        filepath = filters['path']+band
        
        # If the filter is missing, ask what to do
        if filepath not in filters['files']:
            
            print('Current filters:',
                  ', '.join(filters['bands']),
                  '\n')
        
            print('No filters match',filepath)
            dl = input('Would you like me to download it? [y/n] ')
            
            if dl.lower()=='y':
                
                # Prompt for new filter
                print('\nA full list of available filters from the\n'\
                      'SVO Filter Profile Service can be found at\n'\
                      'http://svo2.cab.inta-csic.es/theory/fps3/\n')
                band = input('Enter the band name to retrieve (e.g. 2MASS/2MASS.J): ')
                
                # Download the XML (VOTable) file
                baseURL = 'http://svo2.cab.inta-csic.es/svo/theory/fps/fps.php?ID='
                filepath = filter_directory+os.path.basename(band)
                _ = urllib.request.urlretrieve(baseURL+band, filepath)
                
                # Print the new filepath
                print('Band stored as',filepath)
            
        # Try to read filter info
        try:
            
            # Parse the XML file
            vot = vo.parse_single_table(filepath)
            self.rsr = np.array([list(i) for i in vot.array]).T
            
            # Convert to microns
            self.rsr *= np.array([[0.0001],[1.]])
            
            # Parse the filter metadata
            for p in [str(p).split() for p in vot.params]:
                
                # Extract the key/value pairs
                key = p[1].split('"')[1]
                val = p[-1].split('"')[1]
                
                # Do some formatting
                if p[2].split('"')[1]=='float'\
                or p[3].split('"')[1]=='float':
                    val = float(val)
                
                else:
                    val = val.replace('b&apos;','')\
                             .replace('&apos','')\
                             .replace('&amp;','&')\
                             .strip(';')
                
                # Set the attribute
                if key!='Description':
                    setattr(self, key, val)
            
            # Create some attributes
            self.path = filepath
            try:
                self.refs = [self.CalibrationReference.split('=')[-1]]
            except:
                self.refs = []
            
        # If empty, delete XML file
        except:
            
            print('No filter named',band)
            if os.path.isfile(filepath):
                os.remove(filepath)
                
            return
        
    def convolve(self, spectrum):
        """
        Convolve a spectrum with the filter RSR
        
        Parameters
        ----------
        spectrum: array-like
            The wavelength [um] and flux of the spectrum to
            be convolved
            
        Returns
        -------
        np.ndarray
            The convolved spectrum
            
        """
        # Make into iterable arrays
        wav, flx = [np.asarray(i) for i in spectrum]
        dims = list(flx.shape)
        if len(dims)==1:
            flx = np.expand_dims(flx, axis=0)
            
        # Make binned flux array
        bin_dims = dims[:-1]+[len(self.rsr[0])]
        binned = np.zeros(bin_dims)
        
        # Rebin the input spectra to the filter wavelength array
        for n,f in enumerate(flx):
            binned[n] = rebin_spec([wav, f], self.rsr[0])
        
        # Convolve the RSR and spectrum
        binned *= self.rsr[1]
        
        # Restore original shape
        binned = binned.reshape(bin_dims)
        
        return binned
    
    def info(self):
        """
        Print a table of info about the current filter
        """
        # Get the info from the class 
        info = [[k,str(v)] for k,v in vars(self).items() if isinstance(v, (int,float,str,bytes))]
        
        # Print a nice table
        at.Table(np.asarray(info).reshape(len(info),2), names=['Attributes','Values']).pprint(max_width=500, align=['>','<'])
        
def filter_list(filter_directory=pkg_resources.resource_filename('ExoCTK', 'data/filters/')):
    """
    Get a list of the available filters
    
    Parameters
    ----------
    filter_directory: str
        The directory containing the filter relative spectral response curves
    
    Returns
    -------
    list
        The list of band names
    """
    files = glob(filter_directory+'*')
    bands = [os.path.basename(b) for b in files]
    
    return {'files':files, 'bands':bands, 'path':filter_directory}

def interp_flux(mu, flux, params, values):
    """
    Interpolate a cube of synthetic spectra for a
    given index of mu
    
    Parameters
    ----------
    mu: int
        The index of the (Teff, logg, FeH, *mu*, wavelength)
        data cube to interpolate
    flux: np.ndarray
        The 5D data array
    params: list
        A list of each free parameter range
    values: list
        A list of each free parameter values
    
    Returns
    -------
    np.array
        The array of new flux values
    """
    # Iterate over each wavelength (-1 index of flux array)
    l = flux.shape[-1]
    flx = np.zeros(l)
    for lam in range(l):
        interp_f = RegularGridInterpolator(params, flux[:,:,:,mu,lam])
        f, = interp_f(values)
        
        flx[lam] = f
    
    return flx

class ModelGrid(object):
    """
    Creates a ModelGrid object which contains a multi-parameter
    grid of model spectra and its references
    
    Attributes
    ----------
    path: str
        The path to the directory of FITS files used to create the ModelGrid
    refs: list, str
        The references for the data contained in the ModelGrid
    teff_rng: tuple
        The range of effective temperatures [K]
    logg_rng: tuple
        The range of surface gravities [dex]
    FeH_rng: tuple
        The range of metalicities [dex]
    wave_rng: array-like
        The wavelength range of the models [um]
    n_bins: int
        The number of bins for the ModelGrid wavelength array
    data: astropy.table.Table
        The table of parameters for the ModelGrid
    
    """
    def __init__(self, model_directory, bibcode='2013A&A...553A...6H',
                 names={'Teff':'PHXTEFF', 'logg':'PHXLOGG',
                       'FeH':'PHXM_H', 'mass':'PHXMASS',
                       'r_eff':'PHXREFF', 'Lbol':'PHXLUM'}):
        """
        Initializes the model grid by creating a table with a column
        for each parameter and ingests the spectra
    
        Parameters
        ----------
        model_directory: str
            The path to the directory of FITS files of spectra,
            which may include a filename with a wildcard caharacter
        bibcode: str, array-like (optional)
            The bibcode or list of bibcodes for this data set
        names: dict (optional)
            A dictionary to rename the table columns. The Phoenix
            model keywords are given as an example
        """
        # Make sure we can use glob if a directory 
        # is given without a wildcard
        if '*' not in model_directory:
            model_directory += '*'
        
        # Create some attributes
        self.path = os.path.dirname(model_directory)+'/'
        self.refs = ''
        self.wave_rng = (0,40)
        self.n_bins = 1E10
        self.array = ''
        
        # Save the refs to a References() object
        if bibcode:
            if isinstance(bibcode, (list,tuple)):
                pass
            elif bibcode and isinstance(bibcode, str):
                bibcode = [bibcode]
            else:
                pass
            
            self.refs = bibcode
            # _check_for_ref_object()
        
        # Get list of spectral intensity files
        files = glob(model_directory)
        filenames = []
        if not files:
            print('No files match',model_directory,'.')
            return
        
        # Parse the FITS headers
        vals, dtypes = [], []
        for f in files:
            if f.endswith('.fits'):
                try:
                    header = fits.getheader(f)
                    keys = np.array(header.cards).T[0]
                    dtypes = [type(i[1]) for i in header.cards]
                    vals.append([header.get(k) for k in keys])
                    filenames.append(f.split('/')[-1])
                except:
                    print(f,'could not be read into the model grid.')
            
        # Fix data types and make the table
        dtypes = [str if d==bool else d for d in dtypes]
        table = at.Table(np.array(vals), names=keys, dtype=dtypes)
        
        # Add the filenames as a column
        table['filename'] = filenames
        
        # Rename any columns
        for new,old in names.items():
            try:
                table.rename_column(old, new)
            except:
                print('No column named',old)
        
        # Remove columns where the values are all the same
        # and store value as attribute instead
        for n in table.colnames:
            val = table[n][0]
            if list(table[n]).count(val) == len(table[n])\
            and n not in ['Teff','logg','FeH']:
                setattr(self, n, val)
                table.remove_column(n)
        
        # Store the table in the data attribute
        self.data = table
        
        # Store the parameter ranges
        self.Teff_rng = (min(table['Teff']),max(table['Teff']))
        self.logg_rng = (min(table['logg']),max(table['logg']))
        self.FeH_rng = (min(table['FeH']),max(table['FeH']))
        self.Teff_vals = np.unique(table['Teff'])
        self.logg_vals = np.unique(table['logg'])
        self.FeH_vals = np.unique(table['FeH'])
        
    def get(self, Teff, logg, FeH):
        """
        Retrieve the wavelength, flux, and effective radius 
        for the spectrum of the given parameters
        
        Parameters
        ----------
        Teff: int
            The effective temperature (K)
        logg: float
            The logarithm of the surface gravity (dex)
        FeH: float
            The logarithm of the ratio of the metallicity 
            and solar metallicity (dex)
        
        Returns
        -------
        dict
            A dictionary of arrays of the wavelength, flux, and 
            mu values and the effective radius for the given model
        
        """
        # See if the model with the desired parameters is witin the grid
        in_grid = all([(Teff>=self.Teff_rng[0])&
                       (Teff<=self.Teff_rng[1])&
                       (logg>=self.logg_rng[0])&
                       (logg<=self.logg_rng[1])&
                       (FeH>=self.FeH_rng[0])&
                       (FeH<=self.FeH_rng[1])])
        
        if in_grid:
            
            # See if the model with the desired parameters is a true grid point
            on_grid = self.data[[(self.data['Teff']==Teff)&
                                 (self.data['logg']==logg)&
                                 (self.data['FeH']==FeH)]]\
                                 in self.data
            
            # Grab the data if the point is on the grid
            if on_grid:
                
                # Get the row index and filepath
                row, = np.where((self.data['Teff']==Teff)
                              & (self.data['logg']==logg)
                              & (self.data['FeH']==FeH))[0]

                filepath = self.path+str(self.data[row]['filename'])

                # Get the flux, mu, and abundance arrays
                raw_flux = fits.getdata(filepath, 0)
                mu = fits.getdata(filepath, 1)
                #abund = fits.getdata(filepath, 2)

                # Construct full wavelength scale and convert to microns
                if self.CRVAL1=='-':
                    # Try to get data from WAVELENGTH extension...
                    raw_wave = np.array(fits.getdata(filepath, ext=-1)).squeeze()
                else:
                    # ...or try to generate it
                    l = len(raw_flux[0])
                    raw_wave = np.array(self.CRVAL1+self.CDELT1*np.arange(l)).squeeze()
            
                # Convert from A to um
                raw_wave *= 1E-4

                # Trim the wavelength and flux arrays
                idx, = np.where(np.logical_and(raw_wave>=self.wave_rng[0],
                                              raw_wave<=self.wave_rng[1]))
                flux = raw_flux[:,idx]
                wave = raw_wave[idx]

                # Make a dictionary of parameters
                # This should really be a core.Spectrum() object!
                spec_dict = dict(zip(self.data.colnames, self.data[row].as_void()))
                spec_dict['wave'] = wave

                # Bin the spectrum if necessary
                if self.n_bins>0 and self.n_bins<len(wave):
                    pass

                spec_dict['flux'] = flux
                spec_dict['mu'] = mu
                #spec_dict['abund'] = abund
                
            # If not on the grid, interpolate to it
            else:
                # Call grid_interp method
                spec_dict = self.grid_interp(Teff, logg, FeH)

            return spec_dict
        
        else:
            print('Teff:', Teff, ' logg:', logg, ' FeH:', FeH, 
                  ' model not in grid.')
            return
    
    def grid_interp(self, Teff, logg, FeH, plot=False):
        """
        Interpolate the grid to the desired parameters
        
        Parameters
        ----------
        Teff: int
            The effective temperature (K)
        logg: float
            The logarithm of the surface gravity (dex)
        FeH: float
            The logarithm of the ratio of the metallicity 
            and solar metallicity (dex)
        plot: bool
            Plot the interpolated spectrum along
            with the 8 neighboring grid spectra
        
        Returns
        -------
        dict
            A dictionary of arrays of the wavelength, flux, and 
            mu values and the effective radius for the given model
        """
        # Load the fluxes
        if isinstance(self.array,str):
            print('Loading flux into table...')
            self.load_flux()
            
        # Get the flux array
        flux = self.array.copy()
        
        # Get the interpolable parameters
        params, values = [], []
        for p,v in zip([self.Teff_vals, self.logg_vals, self.FeH_vals],
                       [Teff, logg, FeH]):
            if len(p)>1:
                params.append(p)
                values.append(v)
        values = np.asarray(values)
        
        # Interpolate flux values at each wavelength
        # using a pool for multiple processes
        processes = 8
        mu_index = range(new_flux.shape[0])
        start = time.time()
        pool = multiprocessing.Pool(processes)
        func = partial(interp_flux, flux=flux, params=params, values=values)
        new_flux = pool.map(func, mu_index)
        pool.close()
        pool.join()
        
        # Clean up and time of execution
        new_flux = np.asarray(new_flux)
        print('Run time in seconds: ', time.time()-start)
        
        if plot:
            # Plot the interpolated spectrum
            plt.loglog(self.wavelength, new_flux[0], c='k', lw=2, label='{}/{}/{}'.format(*values))
            
            # Plot the 8 neighboring spectra
            for i,j,k in [(0,0,0),(0,1,0),(0,0,1),(0,1,1),(1,0,0),(1,1,0),(1,0,1),(1,1,1)]:
                plt.loglog(self.wavelength, flux[nb[0][i],nb[1][j],nb[2][k],0], label='{}/{}/{}'.format(vl[0][i],vl[1][j],vl[2][k]))
            
            plt.legend(loc=0)
        
        # # Interpolate mu value
        # interp_flux = RegularGridInterpolator(params, flux_grid)
        # muz, = interp_muz(np.array(values))
        mu = None
        r_eff = None
        
        # Make a dictionary to return
        grid_point = {'Teff':Teff, 'logg':logg, 'FeH':FeH,
                      'mu': mu, 'r_eff': r_eff,
                      'flux':new_flux, 'wave':self.wavelength}
    
        return grid_point
    
    def load_flux(self):
        """
        Retrieve the flux arrays for all models 
        and load into the ModelGrid.array attribute
        with shape (Teff, logg, FeH, mu, wavelength)
        """
        if isinstance(self.array,str):
            
            # Get array dimensions
            T, G, M = self.Teff_vals, self.logg_vals, self.FeH_vals
            
            # Iterate through rows
            for nt,teff in enumerate(T):
                for ng,logg in enumerate(G):
                    for nm,feh in enumerate(M):
                    
                        try:
                            
                            # Retrieve flux using the `get()` method
                            spec_dict = self.get(teff, logg, feh)
                            flux = spec_dict['flux']
                            
                            # Create array if necessary
                            if isinstance(self.array,str):
                                self.array = np.zeros([len(T),len(G),len(M)]+list(flux.shape))
                                
                            # Add flux to the array
                            self.array[nt,ng,nm] = flux
                            
                            # Get the wavelength array
                            self.wavelength = spec_dict['wave']
                            
                            # Garbage collection
                            del spec_dict, flux
                            
                        except: pass
        else:
            print('Fluxes already loaded. Call as `self.array`.')
        
    def customize(self, Teff_rng=(0,1E4), logg_rng=(0,6), 
                  FeH_rng=(-3,3), wave_rng=(0,40), n_bins=''):
        """
        Trims the model grid by the given ranges in effective temperature,
        surface gravity, and metallicity. Also sets the wavelength range
        and number of bins for retrieved model spectra.
        
        Parameters
        ----------
        Teff_rng: array-like
            The lower and upper inclusive bounds for the effective
            temperature (K)
        logg_rng: array-like
            The lower and upper inclusive bounds for the logarithm of the
            surface gravity (dex)
        FeH_rng: array-like
            The lower and upper inclusive bounds for the logarithm of the
            ratio of the metallicity and solar metallicity (dex)
        wave_rng: array-like
            The lower and upper inclusive bounds for the wavelength (microns)
        n_bins: int
            The number of bins for the wavelength axis
        
        """
        # Make a copy of the grid
        grid = self.data.copy()
        self.wave_rng = wave_rng
        self.n_bins = n_bins or self.n_bins
        
        # Filter grid by given parameters
        self.data = grid[[(grid['Teff']>=Teff_rng[0])
                         & (grid['Teff']<=Teff_rng[1])
                         & (grid['logg']>=logg_rng[0])
                         & (grid['logg']<=logg_rng[1])
                         & (grid['FeH']>=FeH_rng[0])
                         & (grid['FeH']<=FeH_rng[1])]]
                         
        # Print a summary of the returned grid
        print('{}/{}'.format(len(self.data),len(grid)),
              'spectra in parameter range',
              'Teff:', Teff_rng, ', logg:',logg_rng,
              ', FeH:', FeH_rng, ', wavelength:', wave_rng)
        
        # Do nothing if he cut leaves the grid empty
        if len(self.data)==0:
            self.data = grid
            print('The given parameter ranges would leave 0 models in the grid.')
            print('The model grid has not been updated. Please try again.')
            
        # Update the attributes
        self.Teff_rng = (min(self.data['Teff']),max(self.data['Teff']))
        self.logg_rng = (min(self.data['logg']),max(self.data['logg']))
        self.FeH_rng = (min(self.data['FeH']),max(self.data['FeH']))
        self.Teff_vals = np.unique(self.data['Teff'])
        self.logg_vals = np.unique(self.data['logg'])
        self.FeH_vals = np.unique(self.data['FeH'])
        
        # Clear the grid copy from memory
        del grid
        
    def info(self):
        """
        Print the ModelGrid attributes
        """
        for n,v in vars(self).items():
            if type(v) in [int, bytes, bool, str, float, tuple, list]:
                print('{}: {}'.format(n,v))
                
    def reset(self):
        """
        Reset the current grid to the original state
        """
        self = self.__init__(self.path)

def rebin_spec(spec, wavnew, oversamp=100, plot=False):
    """
    Rebin a spectrum to a new wavelength array while preserving 
    the total flux
    
    Parameters
    ----------
    spec: array-like
        The wavelength and flux to be binned
    wavenew: array-like
        The new wavelength array
        
    Returns
    -------
    np.ndarray
        The rebinned flux
    
    """
    wave, flux = spec
    nlam = len(wave)
    x0 = np.arange(nlam, dtype=float)
    x0int = np.arange((nlam-1.)*oversamp + 1., dtype=float)/oversamp
    w0int = np.interp(x0int, x0, wave)
    spec0int = np.interp(w0int, wave, flux)/oversamp

    # Set up the bin edges for down-binning
    maxdiffw1 = np.diff(wavnew).max()
    w1bins = np.concatenate(([wavnew[0]-maxdiffw1], .5*(wavnew[1::]+wavnew[0:-1]), [wavnew[-1]+maxdiffw1]))
    
    # Bin down the interpolated spectrum:
    w1bins = np.sort(w1bins)
    nbins = len(w1bins)-1
    specnew = np.zeros(nbins)
    inds2 = [[w0int.searchsorted(w1bins[ii], side='left'), w0int.searchsorted(w1bins[ii+1], side='left')] for ii in range(nbins)]

    for ii in range(nbins):
        specnew[ii] = np.sum(spec0int[inds2[ii][0]:inds2[ii][1]])
    
    if plot:
        plt.figure()
        plt.loglog(wave, flux, c='b')    
        plt.loglog(wavnew, specnew, c='r')
        
    return specnew

class References(object):
    """
    Creates and manages a References object to track references 
    within an ExoCTK user session
    
    Attributes
    ----------
    bibfile: str
        The path to the bibtex file from which the references will be read
    refs: list
        The list of bibcodes saved during the user session
    database: bibtexparser.bibdatabase.BibDatabase object
        The database of parsed bibtex entries
    bibcodes: list
        The list of all bibcodes in the database
        
    """
    def __init__(self, bibfile=''):
        """
        Initializes an empty References object which points to a
        .bib file
        
        Parameters
        ----------
        bibfile: str
          The path to the bibtex file from which the references will be read
        
        """
        bibfile = bibfile or \
            pkg_resources.resource_filename('ExoCTK', 'data/core/bibtex.bib')
        
        # Attributes for the filepath and references
        self.bibfile = bibfile
        self.refs = []
        
        # Load the bibtex into a database
        bf = open(bibfile)
        self.database = bt.load(bf)
        bf.close()
        
        # The list of all bibcodes in the bibfile
        self.bibcodes = [i['ID'] for i in self.database.entries]
        
    def add(self, bibcode):
        """
        Adds a bibcode to the References object
        
        Parameters
        ----------
        bibcode: str
            The unique compact identifier for the reference to be added
        
        """
        # Check that the bibcode is in the bibtex file
        if bibcode in self.bibcodes:
            self.refs += [bibcode]
            print(bibcode,'added to list of references.')
        
        # Suggest adding it to the bibfile
        else:
            print(bibcode,'not in bibfile at',self.bibfile)
            print('Add the bibtex entry to the file and try agin.')
            
    def remove(self, bibcode):
        """
        Removes a bibcode from the References object
        
        Parameters
        ----------
        bibcode: str
            The unique compact identifier for the reference to be removed
        
        """
        # Check that the bibcode is in the bibtex file
        if bibcode in self.bibcodes:
            self.refs = [r for r in self.refs if r!=bibcode]
            print(bibcode,'removed from list of references.')
        
        # Nothing to remove!
        else:
            print(bibcode,'not in bibfile at',self.bibfile)
                
    def write(self, filepath=''):
        """
        Write the .bib file
        
        Parameters
        ----------
        filepath: str
            The directory to which the .bib file should be written.
            Can be an existing .bib file or just a directory
        
        """
        # Use existing .bib file or create new one
        bibfile = filepath if filepath.endswith('.bib') else filepath+'biblio.bib'

        # Create a new database instance
        final = bt.bibdatabase.BibDatabase()
        
        # Get the relevant bibtex entries
        final.entries = [d for d in self.database.entries 
                         if d['ID'] in list(set(self.refs))]
        
        # Write the bibtex to file
        with open(bibfile, 'w') as out:
            out.write(bt.bwriter.BibTexWriter().write(final))

def multiplot(rows, columns, ylabel='', xlabel='', sharey=True, sharex=True, 
              fontsize=20, figsize=(15, 7), title='', **kwargs):
    """
    Creates subplots with given number or *rows* and *columns*.
    
    Parameters
    ----------
    rows: int
        The number of rows in the figure
    columns: int
        The number of columns in the figure
    ylabel: str, list
        The shared y-label or list of y-labels for each column
    xlabel: str, list
        The shared y-label or list of y-labels for each column
    sharey: bool
        Same y-axis limits
    sharex: bool
        Same x-axis limits
    fontsize: int
        The fontsize to use throughout the figure
    figsize: tuple, list
        The (x,y) dimenstions of the figure
    title: str
        The title of the figure
    Returns
    -------
    list
        A list of the figure and axes objects for the current figure
    
    Example
    -------
    >>> fig, (ax11, ax12, ax13), (ax21, ax22, ax23) = multiplot(2, 3)
    >>> ax11.plot(x, y, label='Row 1, Col 1 Plot')
    """
    # Initialize the plot
    fig, axes = plt.subplots(rows, columns, sharey=sharey, sharex=sharex, figsize=figsize)
    plt.rc('text', usetex=True)
    plt.rc('font', size=fontsize)
    
    # Set the y-label(s)
    if ylabel:
        if isinstance(ylabel, str):
            fig.text(0.04, 0.54, ylabel, ha='center', va='center', rotation='vertical', **kwargs)
        else:
            if columns > 1:
                for a, l in zip(axes, ylabel):
                    a[0].set_ylabel(l, fontsize=fontsize, labelpad=fontsize)
            else:
                for a, l in zip(axes, ylabel):
                    a.set_ylabel(l, fontsize=fontsize, labelpad=fontsize)
    
    # Set the x-label(s)
    if xlabel:
        if isinstance(xlabel, str):
            fig.text(0.54, 0.04, xlabel, ha='center', va='center', **kwargs)
        else:
            if rows > 1:
                for a, l in zip(axes, xlabel):
                    a[0].set_xlabel(l, fontsize=fontsize, labelpad=fontsize)
            else:
                for a, l in zip(axes, xlabel):
                    a.set_xlabel(l, fontsize=fontsize, labelpad=fontsize)
    
    # Plot formatting
    plt.suptitle(title)
    plt.subplots_adjust(right=0.96, top=0.93 if title else 0.96, bottom=0.15, left=0.12, hspace=0, wspace=0)
    fig.canvas.draw()
    
    return [fig] + list(axes)

def writeFITS(filename, extensions, headers=()):
    '''
    Write some data to a new FITS file
    
    Parameters
    ----------
    filename: str
        The filename of the output FITS file
    extensions: dict
        The extension name and associated data to include
        in the file
    headers: array-like
        The (keyword,value,comment) groups for the PRIMARY
        header extension
        
    '''
    # Write the arrays to a FITS file
    prihdu = fits.PrimaryHDU()
    prihdu.name = 'PRIMARY'
    hdulist = fits.HDUList([prihdu])
    
    # Write the header to the PRIMARY HDU
    hdulist['PRIMARY'].header.extend(headers, end=True)
    
    # Write the data to the HDU
    for k,v in extensions.items():
        hdulist.append(fits.ImageHDU(data=v, name=k))
        
    # Write the file
    hdulist.writeto(filename, clobber=True)
    hdulist.close()
    
    # Insert END card to prevent header error
    #hdulist[0].header.tofile(filename, endcard=True, clobber=True)

def smooth(x,window_len=10,window='hanning'):
    """smooth the data using a window with requested size.
    
    This method is based on the convolution of a scaled window with the signal.
    The signal is prepared by introducing reflected copies of the signal 
    (with the window size) in both ends so that transient parts are minimized
    in the begining and end part of the output signal.
    
    input:
        x: the input signal 
        window_len: the dimension of the smoothing window
        window: the type of window from 'flat', 'hanning', 'hamming', 'bartlett', 'blackman'
            flat window will produce a moving average smoothing.

    output:
        the smoothed signal
        
    example:

    t=linspace(-2,2,0.1)
    x=sin(t)+randn(len(t))*0.1
    y=smooth(x)
    
    see also: 
    
    numpy.hanning, numpy.hamming, numpy.bartlett, numpy.blackman, numpy.convolve
    scipy.signal.lfilter
 
    TODO: the window parameter could be the window itself if an array instead of a string

	Source: http://www.scipy.org/Cookbook/SignalSmooth		2009-03-13 
    """

    if x.ndim != 1:
        raise ValueError("smooth only accepts 1 dimension arrays.")

    if x.size < window_len:
        raise ValueError("Input vector needs to be bigger than window size.")


    if window_len<3:
        return x


    if not window in ['flat', 'hanning', 'hamming', 'bartlett', 'blackman']:
        raise ValueError("Window is one of 'flat', 'hanning', 'hamming', 'bartlett', 'blackman'")


    #s=numpy.r_[2*x[0]-x[window_len:1:-1],x,2*x[-1]-x[-1:-window_len:-1]]
    s=np.r_[2*np.median(x[0:window_len/5])-x[window_len:1:-1],x,2*np.median(x[-window_len/5:])-x[-1:-window_len:-1]]
    #print(len(s))
    if window == 'flat': #moving average
        w=ones(window_len,'d')
    else:
        w=eval('np.'+window+'(window_len)')

    y=np.convolve(w/w.sum(),s,mode='same')
    return y[window_len-1:-window_len+1]

def medfilt(x, window_len):
    """
    Apply a length-k median filter to a 1D array x.
    Boundaries are extended by repeating endpoints.
    
    Parameters
    ----------
    x: np.array
        The 1D array to smooth
    window_len: int
        The size of the smoothing window
    
    Returns
    -------
    np.ndarray
        The smoothed 1D array
    """
    # assert x.ndim == 1, "Input must be one-dimensional."
    if window_len % 2 == 0:
        print("Median filter length ("+str(window_len)+") must be odd. Adding 1.")
        window_len += 1
    window_len = int(window_len)
    k2 = int((window_len - 1)//2)
    s = np.r_[2*np.median(x[0:int(window_len/5)])-x[window_len:1:-1],x,2*np.median(x[int(-window_len/5):])-x[-1:-window_len:-1]]
    y = np.zeros((len(s), window_len), dtype=s.dtype)
    
    y[:,k2] = s
    for i in range (k2):
        j = k2 - i
        y[j:,i] = s[:-j]
        y[:j,i] = s[0]
        y[:-j,-(i+1)] = s[j:]
        y[-j:,-(i+1)] = s[-1]
    return np.median(y[window_len-1:-window_len+1], axis=1)

def find_closest(axes, points, n=1, values=False):
    """
    Find the n-neighboring elements of a given value in an array
        
    Parameters
    ----------
    axes: list, np.array
        The array(s) to search
    points: array-like, float
        The point(s) to search for
    n: int
        The number of values to the left and right of the points
    Returns
    -------
    np.ndarray
        The n-values to the left and right of 'points' in 'axes'
    """
    results = []
    if not isinstance(axes,list):
        axes = list(axes)
        
    for i,(axis,point) in enumerate(zip(axes,points)):
        if point>=min(axis) and point<=max(axis):
            axis = np.asarray(axis)
            idx = np.clip(axis.searchsorted(point), 1, len(axis)-1)
        
            if values:
                result = axis[max(0,idx-n):min(idx+n,len(axis))]
            else:
                result = np.arange(0,len(axis))[max(0,idx-n):min(idx+n,len(axis))].astype(int)
                
            results.append(result)
        else:
            print('Point {} outside grid.'.format(point))
            return

    return results
