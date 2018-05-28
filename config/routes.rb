Rails.application.routes.draw do
  passwordless_for :users

  root "trophies#index"

  resources :competitions, only: [:create, :new]
  resource :my_profile, only: [:edit, :update], controller: :profile
  resources :trophies
end
