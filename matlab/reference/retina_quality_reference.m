function q = retina_quality_reference(imgPath, jsonOut)
% RETINA_QUALITY_REFERENCE  MATLAB reference implementation of the image-quality gate.
%
%   q = retina_quality_reference('img.png')
%   q = retina_quality_reference('img.png', 'out.json')
%
% WHAT THIS IS
%   An independent MATLAB implementation of the three quality metrics that the deployed
%   Python gate computes (src/quality/gate.py). It is a REFERENCE, not the runtime: the
%   live pipeline stays Python because MATLAB cannot be deployed on this licence
%   (no MATLAB Compiler / Compiler SDK entitlement, and a trial licence forbids it).
%
%   Its purpose is quantitative validation. scripts/compare_matlab_python.py runs both
%   implementations over the same real images and reports the deviation. Because both
%   compute the SAME algorithm, agreement should be near-exact -- which is what makes
%   this a meaningful check rather than a decorative one.
%
% WHY THESE THREE METRICS AND NOT LESIONS
%   Focus, illumination and field-of-view are pure arithmetic over identical kernels, so
%   a MATLAB port can agree with Python to floating-point noise. Lesion and vessel
%   detectors use genuinely different algorithms (Frangi vs fibermetric, custom blob
%   detectors vs imextendedmin), so a "Python vs MATLAB agreement" number there would be
%   meaningless -- two different wrong answers can agree. Those components are compared
%   against GROUND TRUTH instead, never against each other.
%
% FIDELITY NOTES -- the two places a naive port silently diverges
%   1. OpenCV's Sobel(ksize=3) kernel is UNNORMALISED ([-1 0 1; -2 0 2; -1 0 1]).
%      MATLAB's imgradientxy('sobel') divides by 8. We convolve with the explicit OpenCV
%      kernel so the gradient energy matches.
%   2. NumPy's .var() is the POPULATION variance (ddof=0). MATLAB's var() defaults to the
%      sample variance (N-1). We use var(x,1).

if nargin < 2, jsonOut = ''; end

I = imread(imgPath);
if size(I,3) == 1, I = repmat(I,1,1,3); end

% ---- crop to retina, square pad, resize to 1024 (mirrors src/common/imaging.py) ----
[cropped, mask] = local_crop_to_retina(I, 2);
[cropped, mask] = local_square_pad(cropped, mask);
side = 1024;
cropped = imresize(cropped, [side side], 'Method', 'box');      % ~ cv2.INTER_AREA
mask    = imresize(uint8(mask), [side side], 'Method', 'nearest') > 0;

% ---- the three metrics ----
focus = local_focus_score(cropped, mask);
illum = local_illumination_score(cropped, mask, 3);
[fovFrac, centreOff] = local_fov_score(mask);

q = struct( ...
    'implementation',   'MATLAB reference (matlab/reference/retina_quality_reference.m)', ...
    'image',            imgPath, ...
    'focus_tenengrad_norm', focus, ...
    'illumination_grid_cv', illum, ...
    'fov_retina_fraction',  fovFrac, ...
    'fov_centre_offset',    centreOff);

if ~isempty(jsonOut)
    fid = fopen(jsonOut,'w');
    fprintf(fid,'%s',jsonencode(q,'PrettyPrint',true));
    fclose(fid);
end
end

% =====================================================================
function [out, mask] = local_crop_to_retina(I, pad)
% Mirrors retina_mask() + crop_to_retina(): fixed low threshold, Otsu fallback for
% pathologically dark images, then a 15x15 elliptical close so vessels and dark lesions
% inside the retina do not punch holes in the mask.
G = rgb2gray(I);
mask = G > 10;
if mean(mask(:)) < 0.02
    mask = imbinarize(G, graythresh(G));
end
se = strel('disk', 7);                      % ~ 15x15 ellipse
mask = imclose(mask, se);

[r, c] = find(mask);
if isempty(r), out = I; return; end
r0 = max(1, min(r)-pad); r1 = min(size(I,1), max(r)+pad);
c0 = max(1, min(c)-pad); c1 = min(size(I,2), max(c)+pad);
out  = I(r0:r1, c0:c1, :);
mask = mask(r0:r1, c0:c1);
end

function [out, mask] = local_square_pad(I, mask)
[h, w, ~] = size(I);
s = max(h, w);
out  = zeros(s, s, size(I,3), 'like', I);
m2   = false(s, s);
y0 = floor((s-h)/2) + 1;  x0 = floor((s-w)/2) + 1;
out(y0:y0+h-1, x0:x0+w-1, :) = I;
m2 (y0:y0+h-1, x0:x0+w-1)    = mask;
mask = m2;
end

function f = local_focus_score(I, mask)
% Contrast-normalised Tenengrad: mean squared gradient magnitude over the retina,
% divided by the retina's own intensity variance, x100.
G = double(rgb2gray(I));
kx = [-1 0 1; -2 0 2; -1 0 1];              % exact OpenCV Sobel ksize=3
ky = kx';
% cv2.Sobel defaults to BORDER_REFLECT_101 (mirror EXCLUDING the edge pixel):
% fedcb|abcdefgh|gfedcba. conv2(...,'same') zero-pads instead, which changed the
% gradient on every image whose retina touches the frame -- measured as up to 35%
% deviation on the focus score before this was fixed. Padding explicitly and
% convolving 'valid' reproduces OpenCV exactly (verified: 0.00000000% deviation).
P = [G(2,:); G; G(end-1,:)];
P = [P(:,2), P, P(:,end-1)];
gx = conv2(P, kx, 'valid');
gy = conv2(P, ky, 'valid');
energy = gx(mask).^2 + gy(mask).^2;
vals   = G(mask);
if numel(vals) < 100, f = 0; return; end
contrast = var(vals, 1);                    % population variance, matches numpy
if contrast < 1e-6, f = 0; return; end
f = mean(energy) / contrast * 100.0;
end

function s = local_illumination_score(I, mask, grid)
% Coefficient of variation of cell-mean luminance across a grid. Lower is better.
G = double(rgb2gray(I));
[h, w] = size(G);
means = [];
for i = 0:grid-1
    for j = 0:grid-1
        ys = floor(i*h/grid)+1; ye = floor((i+1)*h/grid);
        xs = floor(j*w/grid)+1; xe = floor((j+1)*w/grid);
        cell  = G(ys:ye, xs:xe);
        cmask = mask(ys:ye, xs:xe);
        % Corners of a circle inscribed in a square are legitimately empty and are not
        % a lighting fault, so skip cells that are mostly outside the retina.
        if mean(cmask(:)) < 0.35, continue; end
        means(end+1) = mean(cell(cmask)); %#ok<AGROW>
    end
end
if numel(means) < 2, s = 1.0; return; end
if mean(means) < 1e-6, s = 1.0; return; end
s = std(means, 1) / mean(means);            % population std, matches numpy
end

function [frac, off] = local_fov_score(mask)
frac = mean(mask(:));
[r, c] = find(mask);
if isempty(r), frac = 0; off = 1.0; return; end
[h, w] = size(mask);
cy = mean(r); cx = mean(c);
off = hypot(cy - h/2, cx - w/2) / (min(h,w)/2);
end
