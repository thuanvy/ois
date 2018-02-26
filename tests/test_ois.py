import unittest
import ois
import numpy as np
import os
import varconv


class TestExceptions(unittest.TestCase):
    def setUp(self):
        self.img = np.random.random((100, 100))
        self.ref = np.random.random((100, 100))

    def test_wrong_method_name(self):
        with self.assertRaises(ValueError):
            diff, opt_image, krn, bkg = ois.optimal_system(
                self.img, self.ref, method="WrongName")

    def test_even_side_kernel(self):
        for bad_shape in ((8, 9), (9, 8), (8, 8)):
            with self.assertRaises(ois.EvenSideKernelError):
                ois.optimal_system(self.img, self.ref, bad_shape)

    def test_image_dims(self):
        with self.assertRaises(ValueError):
            diff, opt_image, krn, bkg = ois.optimal_system(
                self.img, np.random.random((10, 10, 100)))
        with self.assertRaises(ValueError):
            diff, opt_image, krn, bkg = ois.optimal_system(
                np.random.random((10, 10, 100)), self.ref)
        with self.assertRaises(ValueError):
            diff, opt_image, krn, bkg = ois.optimal_system(
                np.zeros((5, 5)), np.zeros((7, 7)))

    def test_convolve2d_array_dims(self):
        with self.assertRaises(ValueError):
            ois.convolve2d_adaptive(np.zeros((10, 10, 2)), np.ones((3, 3, 6)), 2)
        with self.assertRaises(ValueError):
            ois.convolve2d_adaptive(np.zeros((10, 10)), np.ones((9, 6)), 2)


class TestSubtract(unittest.TestCase):
    def setUp(self):
        from PIL import Image
        this_dir = os.path.abspath(os.path.dirname(__file__))
        cameraman_path = os.path.join(this_dir, "cameraman.tif")
        self.ref_img = np.array(Image.open(cameraman_path), dtype='float32')
        self.degradereference()

        # Make also the masked versions
        mask = np.zeros(self.image.shape, dtype='bool')
        h, w = mask.shape
        mask[h // 10:h // 10 + 10, w // 10: w // 10 + 10] = True
        mask[:, 50:60] = True
        self.image_masked = np.ma.array(self.image, mask=mask)

        mask_ref = np.zeros(self.ref_img.shape, dtype='bool')
        mask_ref[100:110, 100:110] = True
        mask_ref[200:205, :] = True
        self.ref_img_masked = np.ma.array(self.ref_img, mask=mask_ref)

    def tearDown(self):
        pass

    def degradereference(self):
        from scipy import signal

        # Set some arbitrary kernel to convolve with
        def gauss(shape=(11, 11), center=None, sx=2, sy=2):
            h, w = shape
            if center is None:
                center = ((h - 1) / 2., (w - 1) / 2.)
            x0, y0 = center
            x, y = np.meshgrid(range(w), range(h))
            kernel = np.exp(-0.5 * ((x - x0) ** 2 / sx ** 2 +
                            (y - y0) ** 2 / sy ** 2))
            norm = kernel.sum()
            return kernel / norm

        def createkernel(coeffs, gausslist, kernelshape=(10, 10)):
            kh, kw = kernelshape
            v, u = np.mgrid[:kh, :kw]
            mykernel = np.zeros((kh, kw))
            for aGauss in gausslist:
                if 'modPolyDeg' in aGauss:
                    degmod = aGauss['modPolyDeg']
                else:
                    degmod = 2
                allus = [pow(u, i) for i in range(degmod + 1)]
                allvs = [pow(v, i) for i in range(degmod + 1)]
                if 'center' in aGauss:
                    center = aGauss['center']
                else:
                    center = None
                gaussk = gauss(shape=kernelshape, center=center,
                               sx=aGauss['sx'], sy=aGauss['sy'])
                ind = 0
                for i, aU in enumerate(allus):
                    for aV in allvs[:degmod + 1 - i]:
                        mykernel += coeffs[ind] * aU * aV
                        ind += 1
                mykernel *= gaussk
            # mykernel /= mykernel.sum()
            return mykernel

        # mygausslist = [{'sx': 2., 'sy': 2., 'modPolyDeg': 3},
        # {'sx': 1., 'sy': 3.}, {'sx': 3., 'sy': 1.}]
        self.mygausslist = [{'sx': 2., 'sy': 2., 'modPolyDeg': 3}]
        # mykcoeffs = np.random.rand(10) * 90 + 10
        mykcoeffs = np.array([0., -7.3, 0., 0., 0., 2., 0., 1.5, 0., 0.])

        mykernel = createkernel(mykcoeffs, self.mygausslist,
                                kernelshape=(11, 11))
        # mykernel = gauss()
        kh, kw = mykernel.shape

        self.image = signal.convolve2d(self.ref_img, mykernel, mode='same')

        # Add a varying background:
        self.bkgdeg = 2

        h, w = self.ref_img.shape
        y, x = np.mgrid[:h, :w]
        allxs = [pow(x, i) for i in range(self.bkgdeg + 1)]
        allys = [pow(y, i) for i in range(self.bkgdeg + 1)]

        mybkg = np.zeros(self.ref_img.shape)
        mybkgcoeffs = np.random.rand(6) * 1E-3

        ind = 0
        for i, anX in enumerate(allxs):
            for aY in allys[:self.bkgdeg + 1 - i]:
                mybkg += mybkgcoeffs[ind] * anX * aY
                ind += 1

        self.image += mybkg

    def test_optimal_system_bramich(self):
        # Test Bramich
        diff, ruined_image, optKernel, bkg = ois.optimal_system(
            self.image, self.ref_img, kernelshape=(11, 11),
            bkgdegree=self.bkgdeg, method="Bramich")
        norm_diff = np.linalg.norm(diff) / np.linalg.norm(self.image)
        self.assertLess(norm_diff, 1E-10)
        self.assertFalse(isinstance(diff, np.ma.MaskedArray))
        self.assertFalse(isinstance(ruined_image, np.ma.MaskedArray))
        self.assertFalse(isinstance(bkg, np.ma.MaskedArray))

    def test_optimal_system_alardlp(self):
        # Test Alard & Lupton
        diff, ruined_image, optKernel, bkg = ois.optimal_system(
            self.image, self.ref_img,
            kernelshape=(11, 11),
            bkgdegree=self.bkgdeg,
            method="Alard-Lupton",
            gausslist=self.mygausslist)
        norm_diff = np.linalg.norm(diff) / np.linalg.norm(self.image)
        self.assertLess(norm_diff, 1E-10)
        self.assertFalse(isinstance(diff, np.ma.MaskedArray))
        self.assertFalse(isinstance(ruined_image, np.ma.MaskedArray))
        self.assertFalse(isinstance(bkg, np.ma.MaskedArray))

    def test_optimal_system_adaptivebramich(self):
        # Test Adaptive Bramich
        diff, ruined_image, optKernel, bkg = ois.optimal_system(
            self.image, self.ref_img,
            kernelshape=(11, 11),
            bkgdegree=self.bkgdeg,
            method="AdaptiveBramich",
            poly_degree=2)
        norm_diff = np.linalg.norm(diff) / np.linalg.norm(self.image)
        self.assertLess(norm_diff, 1E-10)
        self.assertFalse(isinstance(diff, np.ma.MaskedArray))
        self.assertFalse(isinstance(ruined_image, np.ma.MaskedArray))
        self.assertFalse(isinstance(bkg, np.ma.MaskedArray))

    def test_optimal_system_alardlp_masks(self):
        # Test Alard & Lupton
        diff, ruined_image, optKernel, bkg = ois.optimal_system(
            self.image_masked, self.ref_img_masked,
            kernelshape=(11, 11),
            bkgdegree=self.bkgdeg,
            method="Alard-Lupton",
            gausslist=self.mygausslist)
        self.assertTrue(isinstance(diff, np.ma.MaskedArray))
        norm_diff = np.linalg.norm(diff.compressed()) \
            / np.linalg.norm(self.image_masked.compressed())
        self.assertLess(norm_diff, 1E-10)
        self.assertTrue(isinstance(ruined_image, np.ma.MaskedArray))
        self.assertFalse(isinstance(bkg, np.ma.MaskedArray))

    def test_subtractongrid_bramich_ri(self):
        # Test Bramich without masks:
        subt_img, o, k, b = ois.optimal_system(self.image, self.ref_img,
                                               kernelshape=(11, 11),
                                               bkgdegree=self.bkgdeg,
                                               gridshape=(1, 1),
                                               method="Bramich")
        norm_diff = np.linalg.norm(subt_img) / np.linalg.norm(self.image)
        self.assertLess(norm_diff, 1E-10)
        self.assertFalse(isinstance(subt_img, np.ma.MaskedArray))
        self.assertFalse(isinstance(o, np.ma.MaskedArray))
        self.assertFalse(isinstance(b, np.ma.MaskedArray))

    def test_subtractongrid_bramich_rmim(self):
        # Test Bramich, image masked, ref masked
        subt_img, o, k, b = ois.optimal_system(self.image_masked,
                                               self.ref_img_masked,
                                               kernelshape=(11, 11),
                                               bkgdegree=self.bkgdeg,
                                               gridshape=(1, 1),
                                               method="Bramich")
        self.assertTrue(isinstance(subt_img, np.ma.MaskedArray))
        norm_diff = np.linalg.norm(subt_img.compressed()) \
            / np.linalg.norm(self.image_masked.compressed())
        self.assertLess(norm_diff, 1E-10)
        self.assertTrue(isinstance(o, np.ma.MaskedArray))
        self.assertFalse(isinstance(b, np.ma.MaskedArray))

    def test_subtractongrid_bramich_rmi(self):
        # Test Bramich image not masked, ref masked
        subt_img, o, k, b = ois.optimal_system(self.image, self.ref_img_masked,
                                               bkgdegree=self.bkgdeg,
                                               kernelshape=(11, 11),
                                               gridshape=(1, 1),
                                               method="Bramich")
        self.assertTrue(isinstance(subt_img, np.ma.MaskedArray))
        norm_diff = np.linalg.norm(subt_img.compressed()) \
            / np.linalg.norm(self.image)
        self.assertLess(norm_diff, 1E-10)
        self.assertTrue(isinstance(o, np.ma.MaskedArray))
        self.assertFalse(isinstance(b, np.ma.MaskedArray))

    def test_subtractongrid_bramich_rim(self):
        # Test Bramich image masked, ref not masked
        subt_img, o, k, b = ois.optimal_system(self.image_masked, self.ref_img,
                                               bkgdegree=self.bkgdeg,
                                               kernelshape=(11, 11),
                                               gridshape=(1, 1),
                                               method="Bramich")
        self.assertTrue(isinstance(subt_img, np.ma.MaskedArray))
        norm_diff = np.linalg.norm(subt_img.compressed()) \
            / np.linalg.norm(self.image_masked.compressed())
        self.assertLess(norm_diff, 1E-10)
        self.assertTrue(isinstance(o, np.ma.MaskedArray))
        self.assertFalse(isinstance(b, np.ma.MaskedArray))

    def test_subtractongrid_alardlp_ri(self):
        # Test Alard & Lupton without masks:
        subt_img, o, k, b = ois.optimal_system(self.image, self.ref_img,
                                               kernelshape=(11, 11),
                                               bkgdegree=self.bkgdeg,
                                               gridshape=(1, 1),
                                               method="Alard-Lupton",
                                               gausslist=self.mygausslist)
        norm_diff = np.linalg.norm(subt_img) / np.linalg.norm(self.image)
        self.assertLess(norm_diff, 1E-10)
        self.assertFalse(isinstance(subt_img, np.ma.MaskedArray))
        self.assertFalse(isinstance(o, np.ma.MaskedArray))
        self.assertFalse(isinstance(b, np.ma.MaskedArray))

    def test_subtractongrid_alardlp_rmim(self):
        # Test Alard & Lupton, image masked, ref masked
        subt_img, o, k, b = ois.optimal_system(self.image_masked,
                                               self.ref_img_masked,
                                               kernelshape=(11, 11),
                                               bkgdegree=self.bkgdeg,
                                               gridshape=(1, 1),
                                               method="Alard-Lupton",
                                               gausslist=self.mygausslist)
        self.assertTrue(isinstance(subt_img, np.ma.MaskedArray))
        norm_diff = np.linalg.norm(subt_img.compressed()) \
            / np.linalg.norm(self.image_masked.compressed())
        self.assertLess(norm_diff, 1E-10)
        self.assertTrue(isinstance(o, np.ma.MaskedArray))
        self.assertFalse(isinstance(b, np.ma.MaskedArray))

    def test_subtractongrid_alardlp_rim(self):
        # Test Alard & Lupton, image masked, ref not masked
        subt_img, o, k, b = ois.optimal_system(self.image_masked, self.ref_img,
                                               kernelshape=(11, 11),
                                               bkgdegree=self.bkgdeg,
                                               gridshape=(1, 1),
                                               method="Alard-Lupton",
                                               gausslist=self.mygausslist)
        self.assertTrue(isinstance(subt_img, np.ma.MaskedArray))
        norm_diff = np.linalg.norm(subt_img.compressed()) \
            / np.linalg.norm(self.image_masked.compressed())
        self.assertLess(norm_diff, 1E-10)
        self.assertTrue(isinstance(o, np.ma.MaskedArray))
        self.assertFalse(isinstance(b, np.ma.MaskedArray))

    def test_subtractongrid_alardlp_rmi(self):
        # Test Alard & Lupton, image not masked, ref masked
        subt_img, o, k, b = ois.optimal_system(self.image, self.ref_img_masked,
                                               kernelshape=(11, 11),
                                               bkgdegree=self.bkgdeg,
                                               gridshape=(1, 1),
                                               method="Alard-Lupton",
                                               gausslist=self.mygausslist)
        self.assertTrue(isinstance(subt_img, np.ma.MaskedArray))
        norm_diff = np.linalg.norm(subt_img.compressed()) \
            / np.linalg.norm(self.image)
        self.assertLess(norm_diff, 1E-10)
        self.assertTrue(isinstance(o, np.ma.MaskedArray))
        self.assertFalse(isinstance(b, np.ma.MaskedArray))

    def test_subtractongrid_adaptive_ri(self):
        deg = 2
        bkg_deg = None
        k_side = 3
        k_shape = (k_side, k_side)
        pol_dof = (deg + 1) * (deg + 2) // 2
        kernel = np.random.random((k_side, k_side, pol_dof))
        image = ois.convolve2d_adaptive(self.ref_img, kernel, deg)
        subt_img, o, k, b = ois.optimal_system(image, self.ref_img,
                                               kernelshape=k_shape,
                                               bkgdegree=bkg_deg,
                                               gridshape=(1, 1),
                                               method="AdaptiveBramich",
                                               poly_degree=deg)
        norm_diff = np.linalg.norm(subt_img) / np.linalg.norm(image)
        self.assertLess(norm_diff, 1E-10)
        self.assertFalse(isinstance(subt_img, np.ma.MaskedArray))
        self.assertFalse(isinstance(o, np.ma.MaskedArray))
        self.assertFalse(isinstance(b, np.ma.MaskedArray))

    def test_subtractongrid_adaptive_rmi(self):
        deg = 2
        bkg_deg = None
        k_side = 3
        k_shape = (k_side, k_side)
        pol_dof = (deg + 1) * (deg + 2) // 2
        kernel = np.random.random((k_side, k_side, pol_dof))
        image = ois.convolve2d_adaptive(self.ref_img, kernel, deg)
        subt_img, o, k, b = ois.optimal_system(image, self.ref_img_masked,
                                               kernelshape=k_shape,
                                               bkgdegree=bkg_deg,
                                               gridshape=(1, 1),
                                               method="AdaptiveBramich",
                                               poly_degree=deg)
        self.assertTrue(isinstance(subt_img, np.ma.MaskedArray))
        norm_diff = np.linalg.norm(subt_img.compressed())\
            / np.linalg.norm(image)
        self.assertLess(norm_diff, 1E-10)
        self.assertTrue(isinstance(o, np.ma.MaskedArray))
        self.assertFalse(isinstance(b, np.ma.MaskedArray))

    def test_convolve2d_adaptive_dtype_check(self):
        kernel = np.random.random((3, 3, 1))
        ois.convolve2d_adaptive(self.ref_img.astype('int32'), kernel, 0)
        ois.convolve2d_adaptive(self.ref_img, kernel.astype('int32'), 0)

    def test_no_background(self):
        diff, ruined_image, optKernel, bkg = ois.optimal_system(
            self.image, self.ref_img,
            kernelshape=(11, 11),
            bkgdegree=None,
            method="Alard-Lupton",
            gausslist=self.mygausslist)
        self.assertEqual(np.linalg.norm(bkg.flatten(), ord=np.inf), 0.0)
        norm_diff = np.linalg.norm(diff) / np.linalg.norm(self.image)
        self.assertLess(norm_diff, 1E-2)

        diff, ruined_image, optKernel, bkg = ois.optimal_system(
            self.image, self.ref_img,
            kernelshape=(11, 11),
            bkgdegree=None,
            method="Bramich")
        self.assertEqual(np.linalg.norm(bkg.flatten(), ord=np.inf), 0.0)
        norm_diff = np.linalg.norm(diff) / np.linalg.norm(self.image)
        self.assertLess(norm_diff, 1E-2)

        diff, ruined_image, optKernel, bkg = ois.optimal_system(
            self.image, self.ref_img,
            kernelshape=(11, 11),
            bkgdegree=None,
            method="AdaptiveBramich",
            poly_degree=1)
        self.assertEqual(np.linalg.norm(bkg.flatten(), ord=np.inf), 0.0)
        norm_diff = np.linalg.norm(diff) / np.linalg.norm(self.image)
        self.assertLess(norm_diff, 1E-2)


class TestVarConv(unittest.TestCase):

    def test_gen_matrix_system_sizes(self):
        deg = 2
        bkg_deg = 0
        k_side = 3
        n, m = 10, 10
        image = np.random.random((n, m))
        refimage = image.copy()
        mm, b, c = varconv.gen_matrix_system(image, refimage, 0, None,
                                             k_side, deg, bkg_deg)
        pol_dof = (deg + 1) * (deg + 2) // 2
        bkg_dof = (bkg_deg + 1) * (bkg_deg + 2) // 2
        k_size = k_side * k_side
        m_dof = pol_dof * k_size + bkg_dof
        self.assertEqual(mm.shape, (m_dof, m_dof))
        self.assertEqual(b.shape, (m_dof,))
        self.assertEqual(c.shape, (k_size, pol_dof, bkg_dof, n * m))

    def test_gen_matrix_system_constantkernel(self):
        deg = 0
        k_side = 3
        n, m = 10, 10
        image = np.random.random((n, m))
        refimage = image.copy()
        mm, b, c = varconv.gen_matrix_system(image, refimage, 0, None,
                                             k_side, deg, -1)
        coeffs = np.linalg.solve(mm, b)
        kc = k_side // 2
        result_kernel = coeffs.reshape((k_side, k_side))
        best_kernel = np.zeros((k_side, k_side))
        best_kernel[kc, kc] = 1.0
        self.assertLess(np.linalg.norm(result_kernel - best_kernel), 1E-10)

    def test_gen_matrix_system_constantkernel_masked(self):
        deg = 0
        k_side = 3
        n, m = 10, 10
        image = np.random.random((n, m))
        refimage = image.copy()
        mask = np.zeros((n, m), dtype='bool')
        mask[3:5, 3:5]
        mm, b, c = varconv.gen_matrix_system(image, refimage, 1, mask,
                                             k_side, deg, -1)
        coeffs = np.linalg.solve(mm, b)
        kc = k_side // 2
        result_kernel = coeffs.reshape((k_side, k_side))
        best_kernel = np.zeros((k_side, k_side))
        best_kernel[kc, kc] = 1.0
        self.assertLess(np.linalg.norm(result_kernel - best_kernel), 1E-10)

    def test_convolve2d_adaptive_idkernel(self):
        kernel = np.zeros((3, 3, 1), dtype="float64")
        kernel[1, 1, 0] = 1.0
        image = np.random.random((10, 10))
        # image = np.arange(100, dtype="float64").reshape((10, 10))
        conv = varconv.convolve2d_adaptive(image, kernel, 0)
        self.assertEqual(conv.shape, image.shape)
        self.assertLess(np.linalg.norm(image - conv), 1E-10)

    def test_convolve2d_adaptive_undoing(self):
        deg = 2
        k_side = 3
        pol_dof = (deg + 1) * (deg + 2) // 2
        kernel = np.random.random((k_side, k_side, pol_dof))
        refimage = np.random.random((10, 10))
        image = varconv.convolve2d_adaptive(refimage, kernel, deg)
        mm, b, c = varconv.gen_matrix_system(image, refimage, 0, None,
                                             k_side, deg, -1)
        coeffs = np.linalg.solve(mm, b)
        result_kernel = coeffs.reshape((k_side, k_side, pol_dof))
        opt_ref = varconv.convolve2d_adaptive(refimage, result_kernel, deg)
        self.assertLess(np.linalg.norm(opt_ref - image, ord=np.inf) /
                        np.linalg.norm(image, ord=np.inf), 1E-8)
        self.assertLess(np.linalg.norm((kernel - result_kernel).flatten(),
                                       ord=np.inf) /
                        np.linalg.norm(kernel.flatten(), ord=np.inf), 1E-8)

    def test_convolve2d_adaptive_cameraman(self):
        from PIL import Image
        this_dir = os.path.abspath(os.path.dirname(__file__))
        cameraman_path = os.path.join(this_dir, "cameraman.tif")
        refimage = np.array(Image.open(cameraman_path), dtype='float64')

        # degrade reference
        deg = 2
        k_side = 3
        pol_dof = (deg + 1) * (deg + 2) // 2
        kernel = np.random.random((k_side, k_side, pol_dof))
        image = varconv.convolve2d_adaptive(refimage, kernel, deg)

        mm, b, c = varconv.gen_matrix_system(image, refimage, 0, None,
                                             k_side, deg, -1)
        coeffs = np.linalg.solve(mm, b)
        result_kernel = coeffs.reshape((k_side, k_side, pol_dof))

        opt_ref = varconv.convolve2d_adaptive(refimage, result_kernel, deg)
        self.assertLess(np.linalg.norm(opt_ref - image, ord=np.inf) /
                        np.linalg.norm(image, ord=np.inf), 1E-8)

    def test_convolve2d_adaptive_cameraman_masked(self):
        from PIL import Image
        this_dir = os.path.abspath(os.path.dirname(__file__))
        cameraman_path = os.path.join(this_dir, "cameraman.tif")
        refimage = np.array(Image.open(cameraman_path), dtype='float64')
        mask = np.zeros(refimage.shape, dtype='bool')
        mask[3:5, 3:5]

        # degrade reference
        deg = 2
        k_side = 3
        pol_dof = (deg + 1) * (deg + 2) // 2
        kernel = np.random.random((k_side, k_side, pol_dof))
        image = varconv.convolve2d_adaptive(refimage, kernel, deg)

        mm, b, c = varconv.gen_matrix_system(image, refimage, 1, mask,
                                             k_side, deg, -1)
        coeffs = np.linalg.solve(mm, b)
        result_kernel = coeffs.reshape((k_side, k_side, pol_dof))

        opt_ref = varconv.convolve2d_adaptive(refimage, result_kernel, deg)
        self.assertLess(np.linalg.norm(opt_ref - image, ord=np.inf) /
                        np.linalg.norm(image, ord=np.inf), 1E-8)

    def test_both_bramich_consistency(self):
        deg = 0
        bkg_deg = 0
        k_side = 3
        image = np.random.random((10, 10))
        refimage = np.random.random((10, 10))
        k_shape = (k_side, k_side)

        diff, opt_img, opt_k, bkg = ois.optimal_system(
            image, refimage, kernelshape=k_shape, bkgdegree=bkg_deg,
            method="Bramich")
        diff, opt_img, opt_vark, bkg = ois.optimal_system(
            image, refimage, kernelshape=k_shape, bkgdegree=bkg_deg,
            method="AdaptiveBramich", poly_degree=deg)

        self.assertEqual(opt_vark.shape, (k_side, k_side, 1))
        opt_vark = opt_vark.reshape((k_side, k_side))

        diff_norm = np.linalg.norm((opt_k - opt_vark).flatten(), ord=np.inf)
        kernel_norm = np.linalg.norm(opt_k.flatten(), ord=np.inf)
        self.assertLess(diff_norm / kernel_norm, 1E-8)

    def test_eval_adpative_kernel(self):
        test_k = np.array([[[ 2.], [ 3.]], [[ 1.], [ 4.]]])
        self.assertLess(np.max(np.abs(ois.eval_adpative_kernel(test_k, 0, 0)
                                      - np.array([[ 2.,  3.],[ 1.,  4.]]))), 1E-10)
        self.assertLess(np.max(np.abs(ois.eval_adpative_kernel(test_k, 0, 1)
                                      - np.array([[ 2.,  3.],[ 1.,  4.]]))), 1E-10)
        self.assertLess(np.max(np.abs(ois.eval_adpative_kernel(test_k, 1, 0)
                                      - np.array([[ 2.,  3.],[ 1.,  4.]]))), 1E-10)
        self.assertLess(np.max(np.abs(ois.eval_adpative_kernel(test_k, 1, 1)
                                      - np.array([[ 2.,  3.],[ 1.,  4.]]))), 1E-10)


if __name__ == "__main__":
    unittest.main()
