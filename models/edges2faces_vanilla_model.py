import torch
from .base_model import BaseModel
from . import networks


class Edges2facesvanillaModel(BaseModel):
	@staticmethod
	def modify_commandline_options(parser, is_train=True):
		"""Add new model-specific options and rewrite default values for existing options.

		Parameters:
			parser -- the option parser
			is_train -- if it is training phase or test phase. You can use this flag to add training-specific or test-specific options.

		Returns:
			the modified parser.
		"""
		parser.set_defaults(norm='batch', netG='unet_256',
							dataset_mode='edges2faces')

		if is_train:
			parser.set_defaults(pool_size=0)
			parser.set_defaults(gan_mode='vanilla')
			parser.add_argument('--lambda_regression', type=float, default=100.0, help='weight for the regression loss')  # You can define new arguments for this model.

		return parser

	def __init__(self, opt):
		"""Initialize this model class.
		Parameters:
			opt -- training/test options
		"""
		BaseModel.__init__(self, opt)  # call the initialization method of BaseModel
		# specify the training losses you want to print out.
		# The program will call base_model.get_current_losses to plot the losses to the console
		# and save them to the disk.
		self.loss_names = ['G_L1', 'G_GAN', 'D_real', 'D_generated']
		# specify the images you want to save and display.
		# The program will call base_model.get_current_visuals to save
		# and display these images.
		if self.isTrain:
			self.visual_names = ['faces', 'edges', 'result']
		else:
			self.visual_names = ['edges', 'result']
		# specify the models you want to save to the disk.
		# The program will call base_model.save_networks and base_model.load_networks to save and load networks.
		# you can use opt.isTrain to specify different behaviors for training and test.
		# For example, some networks will not be used during test, and you don't need to load them.
		if self.isTrain:
			self.model_names = ['G', 'D']
		else:  # during test time, only load G
			self.model_names = ['G']
		# define networks; you can use opt.isTrain to specify different behaviors for training and test.
		self.netG = networks.define_G(opt.input_nc, opt.output_nc, opt.ngf, opt.netG, opt.norm,
									  not opt.no_dropout, opt.init_type, opt.init_gain, gpu_ids=self.gpu_ids)

		if self.isTrain:  # define a discriminator; conditional GANs need to take both input and output images;
			# Therefore, #channels for D is input_nc + output_nc
			self.netD = networks.define_D(opt.input_nc + opt.output_nc, opt.ndf, opt.netD,
			                              opt.n_layers_D, opt.norm, opt.init_type, opt.init_gain, self.gpu_ids)

		if self.isTrain:
			self.criterionL1 = torch.nn.L1Loss()
			self.criterionGAN = networks.GANLoss(opt.gan_mode).to(self.device)
			# define and initialize optimizers.
			self.optimizer_G = torch.optim.Adam(self.netG.parameters(), lr=opt.lr, betas=(opt.beta1, 0.999))
			self.optimizer_D = torch.optim.Adam(self.netD.parameters(), lr=opt.lr, betas=(opt.beta1, 0.999))
			self.optimizers.append(self.optimizer_G)
			self.optimizers.append(self.optimizer_D)

		# Our program will automatically call <model.setup> to define schedulers, load networks, and print networks

	def set_input(self, input):
		"""Unpack input data from the dataloader and perform necessary pre-processing steps.

		Parameters:
			input: a dictionary that contains the data itself and its metadata information.
		"""
		self.edges = input['data_A'].to(self.device)  # get image data A
		if self.isTrain:
			self.faces = input['data_B'].to(self.device)  # get image data B
		self.image_paths = input['path']  # get image paths

	def forward(self):
		"""Run forward pass. This will be called by both functions <optimize_parameters> and <test>."""
		self.result = self.netG(self.edges)  # generate output image given the input data_A

	def backward_D(self):
		"""Calculate losses, gradients, and update network weights; called in every training iteration"""
		# Fake
		generated = torch.cat((self.edges, self.result), 1)  # we use conditional GANs; we need to feed both input and output to the discriminator
		pred_generated = self.netD(generated.detach())
		self.loss_D_generated = self.criterionGAN(pred_generated, False)
		# Real
		real = torch.cat((self.edges, self.faces), 1)
		pred_real = self.netD(real)
		self.loss_D_real = self.criterionGAN(pred_real, True)
		# combine loss and calculate gradients
		self.loss_D = (self.loss_D_generated + self.loss_D_real) * 0.5
		self.loss_D.backward()

	def backward_G(self):
		# First, the generated image should fake the discriminator
		generated = torch.cat((self.edges, self.result), 1)
		pred_generated = self.netD(generated)
		self.loss_G_GAN = self.criterionGAN(pred_generated, True)
		# Second, G(A) = B
		self.loss_G_L1 = self.criterionL1(self.result, self.faces) * self.opt.lambda_regression
		# combine loss and calculate gradients
		self.loss_G = self.loss_G_GAN + self.loss_G_L1
		self.loss_G.backward()

	def optimize_parameters(self):
		"""Update network weights; it will be called in every training iteration."""
		self.forward()               # first call forward to calculate intermediate results
		# Update D
		self.set_requires_grad(self.netD, True) # enable backprop for D
		self.optimizer_D.zero_grad()   # clear network G's existing gradients
		self.backward_D()              # calculate gradients for network D
		self.optimizer_D.step()        # update gradients for network D
		# Update g
		self.set_requires_grad(self.netD, False)
		self.optimizer_G.zero_grad()  # clear network G's existing gradients
		self.backward_G()  # calculate gradients for network G
		self.optimizer_G.step()  # update gradients for network G
