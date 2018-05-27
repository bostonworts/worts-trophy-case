Rails.application.routes.draw do
  passwordless_for :users

  root "trophies#index"

  resource :my_profile, only: [:edit, :update], controller: :profile
  resources :trophies, only: [:create, :index, :new]
end
