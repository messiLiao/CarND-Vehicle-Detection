import sys
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import numpy as np
import cv2
import glob
from pathlib import Path
import time
from sklearn.svm import LinearSVC, SVC
from sklearn.preprocessing import StandardScaler
from skimage.feature import hog
from scipy.ndimage.measurements import label as lb
# NOTE: the next import is only valid for scikit-learn version <= 0.17
# for scikit-learn >= 0.18 use:
from sklearn.model_selection import train_test_split
# from sklearn.cross_validation import train_test_split

import matplotlib.image as mpimg
import numpy as np
import cv2
from skimage.feature import hog
import pickle
import argparse
# Define a function to return HOG features and visualization
def get_hog_features(img, orient, pix_per_cell, cell_per_block, 
                        vis=False, feature_vec=True):
    # Call with two outputs if vis==True
    if vis == True:
        features, hog_image = hog(img, orientations=orient, 
                                  pixels_per_cell=(pix_per_cell, pix_per_cell),
                                  block_norm= 'L2-Hys',
                                  cells_per_block=(cell_per_block, cell_per_block), 
                                  transform_sqrt=True, 
                                  visualise=vis, feature_vector=feature_vec)
        return features, hog_image
    # Otherwise call with one output
    else:      
        features = hog(img, orientations=orient, 
                       pixels_per_cell=(pix_per_cell, pix_per_cell),
                       cells_per_block=(cell_per_block, cell_per_block), 
                       block_norm= 'L2-Hys',
                       transform_sqrt=True, 
                       visualise=vis, feature_vector=feature_vec)
        return features

# Define a function to compute binned color features  
def bin_spatial(img, size=(32, 32)):
    # Use cv2.resize().ravel() to create the feature vector
    features = cv2.resize(img, size).ravel() 
    # Return the feature vector
    return features

# Define a function to compute color histogram features 
# NEED TO CHANGE bins_range if reading .png files with mpimg!
def color_hist(img, nbins=32, bins_range=(0, 256)):
    # Compute the histogram of the color channels separately
    channel1_hist = np.histogram(img[:,:,0], bins=nbins, range=bins_range)
    channel2_hist = np.histogram(img[:,:,1], bins=nbins, range=bins_range)
    channel3_hist = np.histogram(img[:,:,2], bins=nbins, range=bins_range)
    # Concatenate the histograms into a single feature vector
    hist_features = np.concatenate((channel1_hist[0], channel2_hist[0], channel3_hist[0]))
    # Return the individual histograms, bin_centers and feature vector
    return hist_features

# Define a function to extract features from a list of images
# Have this function call bin_spatial() and color_hist()
def extract_features(imgs, color_space='RGB', spatial_size=(32, 32),
                        hist_bins=32, orient=9, 
                        pix_per_cell=8, cell_per_block=2, hog_channel=0,
                        spatial_feat=True, hist_feat=True, hog_feat=True):
    # Create a list to append feature vectors to
    features = []
    # Iterate through the list of images
    print_feat = True
    for img_fn in imgs:
        # Read in each one by one
        img = mpimg.imread(str(img_fn))
        feature = single_img_features(img, color_space, spatial_size,
                        hist_bins, orient, 
                        pix_per_cell, cell_per_block, hog_channel,
                        spatial_feat, hist_feat, hog_feat)
        features.append(feature)
        if print_feat:
            print(['feature length:', len(feature)])
            print_feat = False
    # Return list of feature vectors
    return features
    
# Define a function that takes an image,
# start and stop positions in both x and y, 
# window size (x and y dimensions),  
# and overlap fraction (for both x and y)
def slide_window(img, x_start_stop=[None, None], y_start_stop=[None, None], 
                    xy_window=(64, 64), xy_overlap=(0.5, 0.5)):
    # If x and/or y start/stop positions not defined, set to image size
    if x_start_stop[0] == None:
        x_start_stop[0] = 0
    if x_start_stop[1] == None:
        x_start_stop[1] = img.shape[1]
    if y_start_stop[0] == None:
        y_start_stop[0] = 0
    if y_start_stop[1] == None:
        y_start_stop[1] = img.shape[0]
    # Compute the span of the region to be searched    
    xspan = x_start_stop[1] - x_start_stop[0]
    yspan = y_start_stop[1] - y_start_stop[0]
    # Compute the number of pixels per step in x/y
    nx_pix_per_step = np.int(xy_window[0]*(1 - xy_overlap[0]))
    ny_pix_per_step = np.int(xy_window[1]*(1 - xy_overlap[1]))
    # Compute the number of windows in x/y
    nx_buffer = np.int(xy_window[0]*(xy_overlap[0]))
    ny_buffer = np.int(xy_window[1]*(xy_overlap[1]))
    nx_windows = np.int((xspan-nx_buffer)/nx_pix_per_step) 
    ny_windows = np.int((yspan-ny_buffer)/ny_pix_per_step) 
    # Initialize a list to append window positions to
    window_list = []
    # Loop through finding x and y window positions
    # Note: you could vectorize this step, but in practice
    # you'll be considering windows one by one with your
    # classifier, so looping makes sense
    for ys in range(ny_windows):
        for xs in range(nx_windows):
            # Calculate window position
            startx = xs*nx_pix_per_step + x_start_stop[0]
            endx = startx + xy_window[0]
            starty = ys*ny_pix_per_step + y_start_stop[0]
            endy = starty + xy_window[1]
            
            # Append window position to list
            window_list.append(((startx, starty), (endx, endy)))
    # Return the list of windows
    return window_list

# Define a function to draw bounding boxes
def draw_boxes(img, bboxes, color=(0, 0, 255), thick=6):
    # Make a copy of the image
    imcopy = np.copy(img)
    # Iterate through the bounding boxes
    for bbox in bboxes:
        # Draw a rectangle given bbox coordinates
        cv2.rectangle(imcopy, bbox[0], bbox[1], color, thick)
    # Return the image copy with boxes drawn
    return imcopy


# Define a function to extract features from a single image window
# This function is very similar to extract_features()
# just for a single image rather than list of images
def single_img_features(img, color_space='RGB', spatial_size=(32, 32),
                        hist_bins=32, orient=9, 
                        pix_per_cell=8, cell_per_block=2, hog_channel=0,
                        spatial_feat=True, hist_feat=True, hog_feat=True):    
    #1) Define an empty list to receive features
    img_features = []
    #2) Apply color conversion if other than 'RGB'
    if color_space != 'RGB':
        if color_space == 'HSV':
            feature_image = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
        elif color_space == 'LUV':
            feature_image = cv2.cvtColor(img, cv2.COLOR_RGB2LUV)
        elif color_space == 'HLS':
            feature_image = cv2.cvtColor(img, cv2.COLOR_RGB2HLS)
        elif color_space == 'YUV':
            feature_image = cv2.cvtColor(img, cv2.COLOR_RGB2YUV)
        elif color_space == 'YCrCb':
            feature_image = cv2.cvtColor(img, cv2.COLOR_RGB2YCrCb)
    else: feature_image = np.copy(img)      
    #3) Compute spatial features if flag is set
    if spatial_feat == True:
        spatial_features = bin_spatial(feature_image, size=spatial_size)
        #4) Append features to list
        img_features.append(spatial_features)
    #5) Compute histogram features if flag is set
    if hist_feat == True:
        hist_features = color_hist(feature_image, nbins=hist_bins)
        #6) Append features to list
        img_features.append(hist_features)
    #7) Compute HOG features if flag is set
    if hog_feat == True:
        if hog_channel == 'ALL':
            hog_features = []
            for channel in range(feature_image.shape[2]):
                hog_feature = get_hog_features(feature_image[:,:,channel], 
                                    orient, pix_per_cell, cell_per_block, 
                                    vis=False, feature_vec=True)
                hog_features.extend(hog_feature)      
        else:
            hog_features = get_hog_features(feature_image[:,:,hog_channel], orient, 
                        pix_per_cell, cell_per_block, vis=False, feature_vec=True)
        #8) Append features to list
        img_features.append(hog_features)

    #9) Return concatenated array of features
    return np.concatenate(img_features)

# Define a function you will pass an image 
# and the list of windows to be searched (output of slide_windows())
def search_windows(img, windows, clf, scaler, color_space='RGB', 
                    spatial_size=(32, 32), hist_bins=32, 
                    hist_range=(0, 256), orient=9, 
                    pix_per_cell=8, cell_per_block=2, 
                    hog_channel=0, spatial_feat=True, 
                    hist_feat=True, hog_feat=True):

    #1) Create an empty list to receive positive detection windows
    on_windows = []
    #2) Iterate over all windows in the list
    for window in windows:
        #3) Extract the test window from original image
        test_img = cv2.resize(img[window[0][1]:window[1][1], window[0][0]:window[1][0]], (64, 64))      
        #4) Extract features for that window using single_img_features()
        features = single_img_features(test_img, color_space=color_space, 
                            spatial_size=spatial_size, hist_bins=hist_bins, 
                            orient=orient, pix_per_cell=pix_per_cell, 
                            cell_per_block=cell_per_block, 
                            hog_channel=hog_channel, spatial_feat=spatial_feat, 
                            hist_feat=hist_feat, hog_feat=hog_feat)
        #5) Scale extracted features to be fed to classifier
        test_features = scaler.transform(np.array(features).reshape(1, -1))
        #6) Predict using your classifier
        prediction = clf.predict(test_features)
        #7) If positive (prediction == 1) then save the window
        if prediction == 1:
            on_windows.append(window)
        else:
            print("not 1")
    #8) Return windows for positive detections
    return on_windows

def convert_color(img, conv='RGB2YCrCb'):
    if conv == 'RGB2YCrCb':
        return cv2.cvtColor(img, cv2.COLOR_RGB2YCrCb)
    if conv == 'BGR2YCrCb':
        return cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
    if conv == 'RGB2LUV':
        return cv2.cvtColor(img, cv2.COLOR_RGB2LUV)

# Define a single function that can extract features using hog sub-sampling and make predictions
def find_cars(img, ystart, ystop, scale, svc, X_scaler, orient, pix_per_cell, cell_per_block, spatial_size, hist_bins):
    
    img = img.astype(np.float32)/255
    
    img_tosearch = img[ystart:ystop,:,:]
    ctrans_tosearch = convert_color(img_tosearch, conv='RGB2YCrCb')
    if scale != 1:
        imshape = ctrans_tosearch.shape
        ctrans_tosearch = cv2.resize(ctrans_tosearch, (np.int(imshape[1]/scale), np.int(imshape[0]/scale)))
        
    ch1 = ctrans_tosearch[:,:,0]
    ch2 = ctrans_tosearch[:,:,1]
    ch3 = ctrans_tosearch[:,:,2]

    # Define blocks and steps as above
    nxblocks = (ch1.shape[1] // pix_per_cell) - cell_per_block + 1
    nyblocks = (ch1.shape[0] // pix_per_cell) - cell_per_block + 1 
    nfeat_per_block = orient*cell_per_block**2
    
    # 64 was the orginal sampling rate, with 8 cells and 8 pix per cell
    window = 64
    nblocks_per_window = (window // pix_per_cell) - cell_per_block + 1
    cells_per_step = 2  # Instead of overlap, define how many cells to step
    nxsteps = (nxblocks - nblocks_per_window) // cells_per_step + 1
    nysteps = (nyblocks - nblocks_per_window) // cells_per_step + 1
    
    # Compute individual channel HOG features for the entire image
    hog1 = get_hog_features(ch1, orient, pix_per_cell, cell_per_block, feature_vec=False)
    hog2 = get_hog_features(ch2, orient, pix_per_cell, cell_per_block, feature_vec=False)
    hog3 = get_hog_features(ch3, orient, pix_per_cell, cell_per_block, feature_vec=False)
    
    found_win_list = []
    for xb in range(nxsteps):
        for yb in range(nysteps):
            ypos = yb*cells_per_step
            xpos = xb*cells_per_step
            # Extract HOG for this patch
            hog_feat1 = hog1[ypos:ypos+nblocks_per_window, xpos:xpos+nblocks_per_window].ravel() 
            hog_feat2 = hog2[ypos:ypos+nblocks_per_window, xpos:xpos+nblocks_per_window].ravel() 
            hog_feat3 = hog3[ypos:ypos+nblocks_per_window, xpos:xpos+nblocks_per_window].ravel() 
            hog_features = np.hstack((hog_feat1, hog_feat2, hog_feat3))

            xleft = xpos*pix_per_cell
            ytop = ypos*pix_per_cell

            # Extract the image patch
            subimg = cv2.resize(ctrans_tosearch[ytop:ytop+window, xleft:xleft+window], (64,64))
            # Get color features
            spatial_features = bin_spatial(subimg, size=spatial_size)
            hist_features = color_hist(subimg, nbins=hist_bins)

            # Scale features and make a prediction
            feature_list = []
            if spatial_feat:
                feature_list.append(spatial_features)
            if hist_feat:
                feature_list.append(hist_features)
            if hog_feat:
                feature_list.append(hog_features)
            test_features = X_scaler.transform(np.hstack(feature_list).reshape(1, -1))
            # test_features = X_scaler.transform(single_img_features(subimg, color_space=color_space, 
            #                     spatial_size=spatial_size, hist_bins=hist_bins, 
            #                     orient=orient, pix_per_cell=pix_per_cell, 
            #                     cell_per_block=cell_per_block, 
            #                     hog_channel=hog_channel, spatial_feat=spatial_feat, 
            #                     hist_feat=hist_feat, hog_feat=hog_feat).reshape(1, -1))

            test_prediction = svc.predict(test_features)
            prediction_prob = svc.decision_function(test_features)
            
            if test_prediction == 1:
                if prediction_prob[0] > 0.5:
                    xbox_left = np.int(xleft*scale)
                    ytop_draw = np.int(ytop*scale)
                    win_draw = np.int(window*scale)
                    top_left = (xbox_left, ytop_draw+ystart)
                    bottom_right = (xbox_left+win_draw,ytop_draw+win_draw+ystart)
                    found_win_list.append((top_left, bottom_right, prediction_prob[0]))
                
    return found_win_list
    
def add_heat(heatmap, bbox_list):
    # Iterate through list of bboxes
    for box in bbox_list:
        # Add += 1 for all pixels inside each bbox
        # Assuming each "box" takes the form ((x1, y1), (x2, y2))
        heatmap[box[0][1]:box[1][1], box[0][0]:box[1][0]] += 1

    # Return updated heatmap
    return heatmap# Iterate through list of bboxes
    
def apply_threshold(heatmap, threshold):
    # Zero out pixels below the threshold
    heatmap[heatmap <= threshold] = 0
    # Return thresholded map
    return heatmap

def draw_labeled_bboxes(img, labels, preframe_bbox_list):
    bbox_list = []
    # Iterate through all detected cars
    for car_number in range(1, labels[1]+1):
        # Find pixels with each car_number label value
        nonzero = (labels[0] == car_number).nonzero()
        # Identify x and y values of those pixels
        nonzeroy = np.array(nonzero[0])
        nonzerox = np.array(nonzero[1])
        # Define a bounding box based on min/max x and y
        x1, y1, x2, y2 = np.min(nonzerox), np.min(nonzeroy), np.max(nonzerox), np.max(nonzeroy)
        
        w, h = x2 - x1, y2 - y1
        if w < 50 or h < 50:
            continue

        bbox = ((x1, y1), (x2, y2))
        bbox_list.append(bbox)

        found = True
        for frame_bbox in preframe_bbox_list:
            overlap = False
            for rect in frame_bbox:
                w0, h0 = get_overlap(bbox, rect)
                if w0 < 50 or h0 < 50:
                    continue
                else:
                    overlap = True
                    break
            if overlap:
                continue
            else:
                found = False
                break
        if not found:
            continue
        # Draw the box on the image
        cv2.rectangle(img, bbox[0], bbox[1], (0,0,255), 6)

    # Return the image
    return bbox_list

def read_dataset():
    pass
    # Read in cars and notcars
    import dataset
    cars_path = Path(dataset.path) / "vehicles"
    notcars_path = Path(dataset.path) / "non-vehicles"
    cars = list(cars_path.glob("*/*.png"))
    notcars = list(notcars_path.glob("*/*.png"))
    print("cars:{0}, notcars:{1}".format(len(cars), len(notcars)))

    # Reduce the sample size because
    # The quiz evaluator times out after 13s of CPU time
    sample_size = min(len(cars), len(notcars))
    cars = cars[0:sample_size]
    notcars = notcars[0:sample_size]
    return cars, notcars


### TODO: Tweak these parameters and see how the results change.
color_space = 'YCrCb' # Can be RGB, HSV, LUV, HLS, YUV, YCrCb
orient = 9  # HOG orientations
pix_per_cell = 8 # HOG pixels per cell
cell_per_block = 2 # HOG cells per block
hog_channel = 'ALL' # Can be 0, 1, 2, or "ALL"
spatial_size = (32, 32) # Spatial binning dimensions
hist_bins = 32    # Number of histogram bins
spatial_feat = True # Spatial features on or off
hist_feat = True # Histogram features on or off
hog_feat = True # HOG features on or off
y_start_stop = [400, 656] # Min and max in y to search in slide_window()
svm_c = 0.1
svm_gamma = 100
svm_loss = 'hinge'
svm_penalty = 'l2'
sample_size = 8700
linear_svc_model_fn = Path("./saver/linear_svc.model")
feature_scaler_fn = Path("./saver/feature.scaler")
param_fn = Path("./saver/parameters.pickle")
car_features_fn = Path("./saver/car_features.array")
notcar_features_fn = Path("./saver/notcar_features.array")


def load_parameters():
    pass
    t=time.time()
    if not param_fn.exists():
        parameters = dict({})
        parameters['color_space'] = color_space
        parameters['orient'] = orient
        parameters['pix_per_cell'] = pix_per_cell
        parameters['cell_per_block'] = cell_per_block
        parameters['hog_channel'] = hog_channel
        parameters['spatial_size'] = spatial_size
        parameters['hist_bins'] = hist_bins
        parameters['spatial_feat'] = spatial_feat
        parameters['hist_feat'] = hist_feat
        parameters['hog_feat'] = hog_feat
        parameters['y_start_stop'] = y_start_stop
        parameters['svm_c'] = str(svm_c)
        parameters['svm_gamma'] = svm_gamma
        parameters['svm_loss'] = svm_loss
        parameters['svm_penalty'] = svm_penalty
        parameters['sample_size'] = sample_size
        pickle.dump(parameters, param_fn.open('wb'))
    else:
        parameters  = pickle.load(param_fn.open('rb'))

    return parameters

def save_parameters(parameters):
    parameters['color_space'] = color_space
    parameters['orient'] = orient
    parameters['pix_per_cell'] = pix_per_cell
    parameters['cell_per_block'] = cell_per_block
    parameters['hog_channel'] = hog_channel
    parameters['spatial_size'] = spatial_size
    parameters['hist_bins'] = hist_bins
    parameters['spatial_feat'] = spatial_feat
    parameters['hist_feat'] = hist_feat
    parameters['hog_feat'] = hog_feat
    parameters['y_start_stop'] = y_start_stop
    parameters['svm_c'] = str(svm_c)
    parameters['svm_gamma'] = svm_gamma
    parameters['svm_loss'] = svm_loss
    parameters['svm_penalty'] = svm_penalty
    parameters['sample_size'] = sample_size
    pickle.dump(parameters, param_fn.open('wb'))
    return True

def feature_params_changed(parameters):
    changed = \
        parameters['color_space'] != color_space or \
        parameters['orient'] != orient or \
        parameters['pix_per_cell'] != pix_per_cell or \
        parameters['cell_per_block'] != cell_per_block or \
        parameters['hog_channel'] != hog_channel or \
        parameters['spatial_size'] != spatial_size or \
        parameters['hist_bins'] != hist_bins or \
        parameters['spatial_feat'] != spatial_feat or \
        parameters['hist_feat'] != hist_feat or \
        parameters['hog_feat'] != hog_feat
    return changed

def svm_params_changed(parameters):    
    changed = \
        parameters['svm_c'] != str(svm_c) or \
        parameters['svm_gamma'] != svm_gamma or \
        parameters['svm_loss'] != svm_loss or \
        parameters['svm_penalty'] != svm_penalty or \
        parameters['sample_size'] != sample_size
    return changed

def train_svc_model(arg):
    parameters = load_parameters()

    feature_parameters_changed = feature_params_changed(parameters)

    # extract feature when parameters changed and features file not exists.
    need_to_extract = feature_parameters_changed or (not car_features_fn.exists()) or (not notcar_features_fn.exists())
    if need_to_extract:
        print("need to extract images features")
        cars, notcars = read_dataset()
        if feature_parameters_changed or (not car_features_fn.exists()):
            # extract car features
            print("extracting car features")
            t=time.time()
            car_features = extract_features(cars, color_space=color_space, 
                                    spatial_size=spatial_size, hist_bins=hist_bins, 
                                    orient=orient, pix_per_cell=pix_per_cell, 
                                    cell_per_block=cell_per_block, 
                                    hog_channel=hog_channel, spatial_feat=spatial_feat, 
                                    hist_feat=hist_feat, hog_feat=hog_feat)

            t2 = time.time()
            print(round(t2-t, 2), 'Seconds to extract features of cars')
            car_features = np.vstack(car_features)
            car_features.tofile(str(car_features_fn))
        else:
            car_features = np.fromfile(str(car_features_fn))

        if feature_parameters_changed or (not notcar_features_fn.exists()):
            # extract notcar features
            print("extracting notcar features")
            t=time.time()
            notcar_features = extract_features(notcars, color_space=color_space, 
                                    spatial_size=spatial_size, hist_bins=hist_bins, 
                                    orient=orient, pix_per_cell=pix_per_cell, 
                                    cell_per_block=cell_per_block, 
                                    hog_channel=hog_channel, spatial_feat=spatial_feat, 
                                    hist_feat=hist_feat, hog_feat=hog_feat)

            t2 = time.time()
            print(round(t2-t, 2), 'Seconds to extract features of notcars')

            notcar_features = np.vstack(notcar_features)
            notcar_features.tofile(str(notcar_features_fn))
        else:
            notcar_features = np.fromfile(str(notcar_features_fn))

    else:
        print("load car features from .array file.")
        car_features = np.fromfile(str(car_features_fn)).reshape((8792, 8460))
        notcar_features = np.fromfile(str(notcar_features_fn)).reshape((8792, 8460))
        print("car.shape{}, notcars.shape{}".format(car_features.shape, notcar_features.shape))

        car_features = car_features[:sample_size]
        notcar_features = notcar_features[:sample_size]


    need_to_train = feature_params_changed(parameters) or svm_params_changed(parameters) or (not linear_svc_model_fn.exists()) or (not feature_scaler_fn.exists())
    if need_to_train:
        print("train svc model")
        # Create an array stack of feature vectors
        X = np.vstack((car_features, notcar_features)).astype(np.float64)

        # Define the labels vector
        y = np.hstack((np.ones(len(car_features)), np.zeros(len(notcar_features))))

        # Split up data into randomized training and test sets
        rand_state = np.random.randint(0, 100)
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=rand_state)
            
        # Fit a per-column scaler
        X_scaler = StandardScaler().fit(X_train)
        # Apply the scaler to X
        X_train = X_scaler.transform(X_train)
        X_test = X_scaler.transform(X_test)

        print('Using:',orient,'orientations',pix_per_cell,
            'pixels per cell and', cell_per_block,'cells per block')
        print('Feature vector length:', len(X_train[0]))
        # Use a linear SVC 
        lsvc = LinearSVC(C=svm_c, penalty=svm_penalty, loss=svm_loss)

        # Check the training time for the SVC
        t=time.time()
        lsvc.fit(X_train, y_train)
        t2 = time.time()
        print(round(t2-t, 2), 'Seconds to train LinearSVC...')
        # Check the score of the SVC
        print('Test Accuracy of LinearSVC = ', round(lsvc.score(X_test, y_test), 4))

        pickle.dump(lsvc, linear_svc_model_fn.open('wb'))
        pickle.dump(X_scaler, feature_scaler_fn.open('wb'))
    else:
        print("load svc model from file")
        lsvc = pickle.load(linear_svc_model_fn.open('rb'))
        X_scaler = pickle.load(feature_scaler_fn.open('rb'))
    save_parameters(parameters)
    return lsvc, X_scaler

def get_overlap(rect1, rect2):
    ''' 
    check 2 rectangle are intersected. 
    param :
        rect1: ((x1, y1), (x2, y2))
        rect2: ((x1, y1), (x2, y2))
    '''
    (y1, x1), (y2, x2) = rect1
    x1, x2 = min(x1, x2), max(x1, x2)
    y1, y2 = min(y1, y2), max(y1, y2)
    h1, w1 = y2 - y1, x2 - x1

    (n1, m1), (n2, m2) = rect2
    n1, n2 = min(n1, n2), max(n1, n2)
    m1, m2 = min(m1, m2), max(m1, m2)
    h2, w2 = n2 - n1, m2 - m1

    lx, ly = min(x1, m1), min(y1, n1)
    rx, ry = max(x2, m2), max(y2, n2)
    h, w = ry - ly, rx - lx
    if h < h1 + h2 and w < w1 + w2:
        overlap = True
        ow = w1 + w2 - w
        oh = h1 + h2 - h
    else:
        overlap = False
        ow, oh = 0, 0
    return (oh, ow)

def split_rect_list(rect_list):
    rect_group_list = []
    if len(rect_list) < 1:
        return rect_group_list
    rect_group_list.append(rect_list.pop(0))
    while True:
        if len(rect_list) < 1:
            break
        rect = rect_list.pop(0)
    return rect_group_list

ystart, ystop = y_start_stop
scale = 1.5

def load_svc_model():
    '''
    load trained model from file
    '''
    print("load svc model from file")
    svc = pickle.load(linear_svc_model_fn.open('rb'))
    X_scaler = pickle.load(feature_scaler_fn.open('rb'))
    return svc, X_scaler

def process_image(arg):
    path = Path(arg.input)
    if not path.is_file():
        exit(0)
    svc, X_scaler = load_svc_model()
    image = mpimg.imread(str(path))
    if image.dtype == np.uint8:
        draw_image = image.astype(np.float32) / 255
    else:
        draw_image = np.copy(image)
    subimage = draw_image[:64, :64]
    features = single_img_features(subimage, color_space, spatial_size,
                    hist_bins, orient, 
                    pix_per_cell, cell_per_block, hog_channel,
                    spatial_feat, hist_feat, hog_feat)

    test_features = X_scaler.transform(np.array(features).reshape(1, -1))
    svc.predict(test_features)
    #6) Predict using your classifier
    # prediction = clf.predict(test_features)
    #7) If positive (prediction == 1) then save the window

    # Uncomment the following line if you extracted training
    # data from .png images (scaled 0 to 1 by mpimg) and the
    # image you are searching is a .jpg (scaled 0 to 255)
    # image = image.astype(np.float32)/255

    # windows = slide_window(image, x_start_stop=[None, None], y_start_stop=y_start_stop, 
    #                     xy_window=(64, 64), xy_overlap=(0, 0))

    # hot_windows = search_windows(image, windows, svc, X_scaler, color_space=color_space, 
    #                         spatial_size=spatial_size, hist_bins=hist_bins, 
    #                         orient=orient, pix_per_cell=pix_per_cell, 
    #                         cell_per_block=cell_per_block, 
    #                         hog_channel=hog_channel, spatial_feat=spatial_feat, 
    #                         hist_feat=hist_feat, hog_feat=hog_feat) 
    # print("{}, {}".format(len(windows), len(hot_windows)))                      

    # out_img = draw_boxes(draw_image, windows, color=(0, 0, 255), thick=6)    
    found_win_list = []
    frame = image
    ystart, ystop = 400, 500
    win_list = find_cars(frame, ystart, ystop, 1.0, svc, X_scaler, orient, pix_per_cell, cell_per_block, spatial_size, hist_bins)
    found_win_list.extend(win_list)
    ystart, ystop = 400, 600
    win_list = find_cars(frame, ystart, ystop, 1.5, svc, X_scaler, orient, pix_per_cell, cell_per_block, spatial_size, hist_bins)
    found_win_list.extend(win_list)
    ystart, ystop = 400, 600
    win_list = find_cars(frame, ystart, ystop, 2.0, svc, X_scaler, orient, pix_per_cell, cell_per_block, spatial_size, hist_bins)
    found_win_list.extend(win_list)
    ystart, ystop = 400, 650
    win_list = find_cars(frame, ystart, ystop, 2.5, svc, X_scaler, orient, pix_per_cell, cell_per_block, spatial_size, hist_bins)
    found_win_list.extend(win_list)
    ystart, ystop = 400, 700
    win_list = find_cars(frame, ystart, ystop, 3.0, svc, X_scaler, orient, pix_per_cell, cell_per_block, spatial_size, hist_bins)
    found_win_list.extend(win_list)
    ystart, ystop = 500, 700
    win_list = find_cars(frame, ystart, ystop, 4.0, svc, X_scaler, orient, pix_per_cell, cell_per_block, spatial_size, hist_bins)
    found_win_list.extend(win_list)
    ystart, ystop = 600, 700
    win_list = find_cars(frame, ystart, ystop, 6.0, svc, X_scaler, orient, pix_per_cell, cell_per_block, spatial_size, hist_bins)
    found_win_list.extend(win_list)
    
    out_img = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    draw_image = out_img.copy()
    for (top_left, bottom_right) in found_win_list:
        cv2.rectangle(draw_image, top_left, bottom_right,(0,0,255),6)
        
    cv2.imshow("out_img", draw_image)
    heatmap = np.zeros_like(out_img[:,:,0], dtype=np.uint8)
    add_heat(heatmap, found_win_list)
    heatmap[heatmap<2] = 0
    # heatmap[heatmap<10] = 0
    # heatmap *= 255 // (np.max(heatmap) + 1)
    img, contours, h = cv2.findContours(heatmap,cv2.RETR_TREE,cv2.CHAIN_APPROX_SIMPLE)
    bound_rect_list = []
    draw_heat = out_img.copy()
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        print(['w:', w, ',h:', h])
        bound_rect_list.append(((y, x), (y+h, x+w)))
        cv2.rectangle(draw_heat, (x, y), (x+w, y+h), (255,), 5)
    cv2.imshow("heat", draw_heat)
    key = cv2.waitKey(0) & 0xff
    return out_img
    pass

def process_video(arg):
    svc, X_scaler = load_svc_model()

    cap = cv2.VideoCapture(arg.input)

    if arg.output:
        output_fn = arg.output
        fps = 30  
        size =(1280, 720)
        # cv2.cv.CV_FOURCC('D', 'I', 'V', 'X') = 0x58564944
        # cv2.cv.CV_FOURCC('X', '2', '6', '4') = 0x34363258
        # cv2.cv.CV_FOURCC('H', '2', '6', '4') = 0x34363248
        out = cv2.VideoWriter(output_fn, 0x34363258, fps, size, 1) 
    else:
        out = None

    skip_index = 0
    frame_index = 0
    frame_bbox_list = []
    while cap:
        ret, frame = cap.read()
        if not ret:
            break
        frame_index += 1
        if frame_index < skip_index:
            continue
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # multi-scale cars detect
        found_win_list = []
        ystart, ystop = 400, 500
        win_list = find_cars(frame, ystart, ystop, 1.0, svc, X_scaler, orient, pix_per_cell, cell_per_block, spatial_size, hist_bins)
        found_win_list.extend(win_list)
        ystart, ystop = 400, 600
        win_list = find_cars(frame, ystart, ystop, 1.5, svc, X_scaler, orient, pix_per_cell, cell_per_block, spatial_size, hist_bins)
        found_win_list.extend(win_list)
        ystart, ystop = 400, 600
        win_list = find_cars(frame, ystart, ystop, 2.0, svc, X_scaler, orient, pix_per_cell, cell_per_block, spatial_size, hist_bins)
        found_win_list.extend(win_list)
        ystart, ystop = 400, 650
        win_list = find_cars(frame, ystart, ystop, 2.5, svc, X_scaler, orient, pix_per_cell, cell_per_block, spatial_size, hist_bins)
        found_win_list.extend(win_list)
        ystart, ystop = 400, 700
        win_list = find_cars(frame, ystart, ystop, 3.0, svc, X_scaler, orient, pix_per_cell, cell_per_block, spatial_size, hist_bins)
        found_win_list.extend(win_list)
        ystart, ystop = 500, 700
        win_list = find_cars(frame, ystart, ystop, 4.0, svc, X_scaler, orient, pix_per_cell, cell_per_block, spatial_size, hist_bins)
        found_win_list.extend(win_list)
        ystart, ystop = 600, 700
        win_list = find_cars(frame, ystart, ystop, 6.0, svc, X_scaler, orient, pix_per_cell, cell_per_block, spatial_size, hist_bins)
        found_win_list.extend(win_list)
        
        out_img = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            
        heatmap = np.zeros_like(out_img[:,:,0], dtype=np.uint8)

        heatmap[heatmap<2] = 0

        # draw heatmap 
        add_heat(heatmap, found_win_list)

        # Apply threshold to help remove false positives
        heat = apply_threshold(heatmap,1)

        # Visualize the heatmap when displaying    
        heatmap = np.clip(heat, 0, 255)

        # Find final boxes from heatmap using label function
        labels = lb(heatmap)
        bbox_list = draw_labeled_bboxes(out_img, labels, frame_bbox_list)
        frame_bbox_list.append(bbox_list)
        if len(frame_bbox_list) > 4:
            frame_bbox_list.pop(0)

        cv2.imshow("output", out_img)
        key = cv2.waitKey(10) & 0xff
        if key in [ord('q'), 23]:
            break
        if out:
            out.write(out_img)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="find lane line in image or videos")
    subparsers = parser.add_subparsers(help='commands')

    image_parse = subparsers.add_parser('image', help='calibrate a camera with chessboard pictures')
    image_parse.set_defaults(func=process_image)
    image_parse.add_argument("input", action='store',help='image file or directory.')
    image_parse.add_argument("--output", action='store',help='save result image to another file')

    video_parse = subparsers.add_parser('video', help='calibrate a camera with chessboard pictures')
    video_parse.set_defaults(func=process_video)    
    video_parse.add_argument("input", action='store',help='*.mp4 file or directory.')
    video_parse.add_argument("--output", action='store',help='save result video to another file')
    video_parse.add_argument("--skip", action='store',help='save result video to another file')

    train_parse = subparsers.add_parser('train', help='calibrate a camera with chessboard pictures')
    train_parse.set_defaults(func=train_svc_model)
    train_parse.add_argument("--dataset", action='store',help='save result video to another file')
     
    args = parser.parse_args(sys.argv[1:])

    args.func(args)